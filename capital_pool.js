/* 星循 V1：资金池与买卖金额计算（与 capital_pool.py 同逻辑，纯函数）。 */
(function () {
  const floor2 = x => Math.floor((x + 1e-9) * 100) / 100;
  const round2 = x => Math.round((x + 1e-9) * 100) / 100;

  function parseLimit(text) {
    if (typeof text !== 'string') return null;
    const m = text.match(/([\d.]+)\s*(亿元|万元|元)/);
    if (!m) return null;
    const v = Number(m[1]);
    return v * ({ '亿元': 1e8, '万元': 1e4, '元': 1 }[m[2]]);
  }

  function buyRate(buyPct, tiers, amount) {
    if (Number.isFinite(buyPct)) return Number(buyPct);
    if (!Array.isArray(tiers)) return 0;
    for (const t of tiers) {
      const cond = String(t.condition || '');
      const m = cond.match(/小于([\d.]+)(万元|元)/);
      if (m) {
        const lim = Number(m[1]) * (m[2] === '万元' ? 1e4 : 1);
        if (amount < lim) return Number(t.discount_pct ?? t.original_pct ?? 0);
      }
    }
    return 0;
  }

  function toDays(v, unit) {
    return Number(v) * (unit === '年' ? 365 : unit === '个月' ? 30 : 1);
  }

  function redeemRate(tiers, days) {
    if (!Array.isArray(tiers) || !tiers.length) return 0;
    for (const t of tiers) {
      const cond = String(t.condition || '');
      let lo = 0, loInc = true, hi = Infinity, hiInc = true;
      let m = cond.match(/大于等于([\d.]+)(天|个月|年)/);
      if (m) { lo = toDays(m[1], m[2]); }
      m = cond.match(/小于等于([\d.]+)(天|个月|年)/);
      if (m) { hi = toDays(m[1], m[2]); hiInc = true; }
      else {
        m = cond.match(/小于([\d.]+)(天|个月|年)/);
        if (m) { hi = toDays(m[1], m[2]); hiInc = false; }
      }
      const okLo = loInc ? days >= lo : days > lo;
      const okHi = hiInc ? days <= hi : days < hi;
      if (okLo && okHi) return Number(t.original_pct || 0);
    }
    return 0;
  }

  function conservativeRate(tiers) {
    if (!Array.isArray(tiers)) return 0.5;
    for (const t of tiers) {
      if (String(t.condition || '').includes('大于等于7天') && t.original_pct != null) return Number(t.original_pct);
    }
    return 0.5;
  }

  function poolBudget(totalAssets, poolValue, externalCash, ratio) {
    const target = Number(totalAssets) * Number(ratio);
    const newAllowed = Math.max(0, target - Number(poolValue));
    const used = Math.min(newAllowed, Math.max(0, Number(externalCash) || 0));
    return {
      total_assets: Number(totalAssets), ratio: Number(ratio),
      pool_target: target, pool_value: Number(poolValue),
      over_target: Math.max(0, Number(poolValue) - target),
      new_allowed: newAllowed, external_cash: Math.max(0, Number(externalCash) || 0),
      new_used: used
    };
  }

  function planDay(opts) {
    const o = Object.assign({
      totalAssets: 0, poolCash: 0, positions: [], targets: {}, funds: {},
      externalCash: 0, receivable: 0, ratio: 0.10, minAmount: 10,
      buyBand: 0.01, sellBand: 0.02, priority: 'pro_rata', feeMult: 1, scores: {}
    }, opts || {});
    const positions = o.positions || [];
    const funds = o.funds || {};
    const targets = o.targets || {};
    const sumW = Object.values(targets).reduce((a, b) => a + Number(b || 0), 0);
    if (sumW > 1 + 1e-9) throw Error('目标权重合计不能超过 100%');

    const poolValue = Number(o.poolCash) + positions.reduce((a, p) => a + Number(p.value || 0), 0) + Number(o.receivable || 0);
    const budget = poolBudget(o.totalAssets, poolValue, o.externalCash, o.ratio);
    const investable = poolValue + budget.new_used;
    let spendable = Math.max(0, Number(o.poolCash) + budget.new_used);
    const warnings = [];
    if (budget.over_target > 0) warnings.push(`资金池已超过目标 ${budget.over_target.toFixed(2)} 元：暂停新增投入，不强制卖出。`);

    const posMap = {};
    positions.forEach(p => { posMap[String(p.code)] = p; });
    const rows = [];
    const buys = [];
    const sells = [];
    let sellFees = 0;

    // 未配置持仓也要展示
    positions.forEach(p => {
      if (!(String(p.code) in targets)) {
        rows.push({
          code: String(p.code), name: p.name || String(p.code), weight: null,
          current: Number(p.value || 0), target: Number(p.value || 0),
          delta: 0, action: '未配置', amount: 0, fee: 0, shares: null,
          postValue: Number(p.value || 0), executable: false,
          reason: '未给出目标权重，保持不动（不计入新增投入）'
        });
      }
    });

    Object.keys(targets).forEach(code => {
      const f = funds[code];
      const pos = posMap[code];
      const current = pos ? Number(pos.value || 0) : 0;
      const targetValue = Number(targets[code] || 0) * investable;
      const delta = targetValue - current;
      const row = {
        code, name: f ? f.name : (pos ? pos.name : code), weight: Number(targets[code] || 0),
        current, target: targetValue, delta, action: '无操作', amount: 0,
        fee: 0, shares: null, postValue: current, executable: false, reason: ''
      };
      rows.push(row);
      if (!f) { row.reason = '缺少基金信息'; return; }
      if (!Number.isFinite(f.nav) || f.nav <= 0) { row.reason = '缺少有效净值，不生成交易'; return; }
      if (f.status && String(f.status).includes('暂停')) {
        row.reason = `基金状态为“${f.status}”，不可申购`; return;
      }
      if (delta >= Math.max(o.minAmount, o.buyBand * investable)) {
        buys.push({ row, delta, frac: Number((o.scores || {})[code] || 0) });
      } else if (delta <= -Math.max(o.minAmount, o.sellBand * investable)) {
        if (pos && pos.sellable !== false) {
          sells.push({ row, gap: -delta, pos });
        } else {
          row.reason = '需要减仓，但当前无可卖份额（T+1 确认中）';
        }
      } else {
        row.reason = '偏离在交易带内，不操作';
      }
    });

    sells.forEach(it => {
      const row = it.row, pos = it.pos, f = funds[row.code];
      const amount = Math.min(it.gap, Number(pos.value || 0));
      const unknown = !Number.isFinite(pos.holdDays);
      const pct = unknown ? conservativeRate(f.redeem_tiers) : redeemRate(f.redeem_tiers, pos.holdDays);
      const fee = amount * pct / 100 * o.feeMult;
      row.action = '卖出';
      row.amount = amount;
      row.fee = fee;
      row.shares = amount / f.nav;
      row.postValue = Number(pos.value || 0) - amount;
      row.executable = true;
      row.reason = `目标 ${(row.weight * 100).toFixed(0)}%，超出 ${(amount / Math.max(1e-9, investable) * 100).toFixed(1)}% 权益；` +
        `赎回到账 T+${f.settle_days || 2}` + (unknown ? '；持有期未知，费率按保守估计' : '');
      sellFees += fee;
    });

    const totalWant = buys.reduce((a, b) => a + b.delta, 0);
    if (totalWant > spendable && totalWant > 0) {
      if (o.priority === 'signal' && buys.some(b => b.frac > 0)) {
        const ws = buys.reduce((a, b) => a + b.delta * b.frac, 0);
        buys.forEach(b => { b.alloc = ws > 0 ? spendable * b.delta * b.frac / ws : 0; });
      } else {
        buys.forEach(b => { b.alloc = spendable * b.delta / totalWant; });
      }
      warnings.push(`可用现金 ${spendable.toFixed(2)} 元不足以覆盖全部买点，按 ${o.priority} 分配。`);
    } else {
      buys.forEach(b => { b.alloc = b.delta; });
    }

    buys.forEach(it => {
      const row = it.row, f = funds[row.code];
      let amount = floor2(Math.min(it.alloc, spendable));
      if (amount < o.minAmount) { row.reason = `分配金额 ${amount.toFixed(2)} 元低于最小申购 ${o.minAmount} 元`; return; }
      const limit = parseLimit(f.limit);
      if (limit !== null && amount > limit) {
        amount = floor2(limit);
        row.reason = `受日累计申购限额 ${limit.toFixed(0)} 元限制，已截断；`;
      }
      const rate = buyRate(f.buy_pct, f.buy_tiers, amount) / 100 * o.feeMult;
      const fee = amount - amount / (1 + rate);
      const shares = (amount - fee) / f.nav;
      spendable -= amount;
      row.action = '买入';
      row.amount = amount;
      row.fee = fee;
      row.shares = shares;
      row.postValue = row.current + (amount - fee);
      row.executable = true;
      row.reason = (row.reason || '') +
        `目标 ${(row.weight * 100).toFixed(0)}%，缺口 ${it.delta.toFixed(2)} 元；` +
        `申购费 ${(rate * 100).toFixed(2)}%，${f.confirm || 'T+1'} 确认份额`;
    });

    const buysTotal = rows.filter(r => r.action === '买入').reduce((a, r) => a + r.amount, 0);
    const sellsTotal = rows.filter(r => r.action === '卖出').reduce((a, r) => a + r.amount, 0);
    const fees = rows.reduce((a, r) => a + (r.fee || 0), 0);
    const postCash = Number(o.poolCash) + budget.new_used - buysTotal;
    const postInvested = rows.reduce((a, r) => a + r.postValue, 0);
    const postPool = postCash + postInvested + Number(o.receivable || 0) + sellsTotal - sellFees;
    rows.forEach(r => { r.postWeight = postPool > 0 ? r.postValue / postPool : null; });

    if (postCash < -1e-6) throw Error('资金校验失败：现金为负');
    if (buysTotal > Number(o.poolCash) + budget.new_used + 1e-6) throw Error('资金校验失败：买入超过可用现金');

    return {
      rows, warnings, budget,
      totals: {
        buys: buysTotal, sells: sellsTotal, fees,
        spendable_before: Number(o.poolCash) + budget.new_used,
        post_cash: postCash, post_invested: postInvested, post_pool: postPool,
        post_new_allowed: Math.max(0, budget.pool_target - postPool)
      }
    };
  }

  window.CapitalPool = { poolBudget, planDay, buyRate, redeemRate, parseLimit };
})();
