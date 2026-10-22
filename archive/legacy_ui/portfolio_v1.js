/* 星循 V1：总资产、资金池、今日操作、月度复盘（模拟模式）。 */
(function () {
  const D = window.PORTFOLIO_DATA;
  const S = window.XingxunStore;
  const C = window.CapitalPool;
  if (!D || !S || !C) return;
  const $ = id => document.getElementById(id);
  if (!$('v1-snapshot')) return;
  if (D.feature_flag === false || window.XINGXUN_V1 === false) {
    ['v1-snapshot', 'v1-pool', 'v1-positions', 'v1-plan', 'v1-review']
      .forEach(id => { const e = $(id); if (e) e.hidden = true; });
    return;
  }

  const money = v => (Number.isFinite(v) ? '¥' + v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—');
  const pct = v => (Number.isFinite(v) ? (v * 100).toFixed(1) + '%' : '—');
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const today = () => new Date().toISOString().slice(0, 10);
  const monthNow = () => (D.data_date || today()).slice(0, 7);

  function diary() {
    try {
      const a = S.journal();
      return Array.isArray(a) ? a : [];
    } catch (e) { return []; }
  }

  function profile() {
    let p = S.profile();
    if (!p.broken && !p.initialDate && (p.positions || []).length) {
      // 兼容：早期只有 positions 的档案，补一个基线日期
      p.initialDate = today();
      p.initialPositions = p.positions.map(x => ({ ...x }));
      S.saveProfile(p);
    }
    return p;
  }

  function syncFromDiary() {
    try { S.applyNewEntries(diary()); } catch (e) { $('v1PoolStatus').textContent='账本未更新：'+e.message; }
  }

  function renderSnapshot() {
    const latest = S.latestSnapshot();
    const t = latest ? latest.total_assets : null;
    const month = today().slice(0, 7);
    const info = $('v1SnapInfo');
    if (!latest) {
      info.innerHTML = '<span class="v1-warn">尚未录入总金融资产：资金池与买卖金额暂不可计算。</span>';
    } else {
      const stale = latest.date.slice(0, 7) !== month;
      info.innerHTML = `上次确认：<b>${esc(latest.date)}</b> · ${money(t)}` +
        (stale ? '<div class="v1-warn">本月尚未更新，以下计算沿用该金额；请尽快更新。</div>'
               : '<div class="v1-mini">数据来源：手动录入</div>');
    }
    return latest;
  }

  function positionRows(p) {
    return S.valuePositions(p.positions || [], D.funds);
  }

  function renderPositions() {
    const p = profile();
    const v = positionRows(p);
    const body = $('v1PositionsBody');
    const codes = D.allocation.codes || Object.keys(D.allocation.weights);
    const extra = v.rows.filter(r => !codes.includes(r.code));
    const all = [...codes.map(c => v.rows.find(r => r.code === c) || { code: c, name: D.funds[c].name, shares: 0, value: 0, priced: true, nav: D.funds[c].nav }),
                 ...extra];
    body.innerHTML = all.map(r => {
      const f = D.funds[r.code] || {};
      const status = !r.priced ? '<span class="v1-warn" style="display:inline-block;padding:2px 6px">待更新</span>'
        : (r.unknown ? '份额待补' : '正常');
      return `<tr data-code="${esc(r.code)}">
        <td>${esc(f.label || r.name || r.code)} <span class="v1-mini">${esc(r.code)}</span></td>
        <td><input class="v1-shares" type="number" min="0" step="0.01" value="${Number(r.shares || 0).toFixed(2)}" style="width:100px"></td>
        <td class="v1-num">${r.priced ? Number(r.nav).toFixed(4) + '<div class="v1-mini">' + esc(r.nav_date) + '</div>' : '—'}</td>
        <td class="v1-num">${r.priced ? money(r.value) : '—'}</td>
        <td>${status}</td></tr>`;
    }).join('');
    return v;
  }

  function renderPool() {
    const latest = S.latestSnapshot();
    const p = profile();
    const v = positionRows(p);
    const receivable = Number(p.receivable || 0);
    const cash = Number(p.poolCash || 0);
    const poolValue = cash + Number(p.frozenCash||0) + v.total + receivable;
    $('v1SettleTrade').innerHTML=Object.entries(p.payments||{}).filter(([id,v])=>!v.settled).map(([id,v])=>`<option value="${esc(id)}">${esc(id)} · ${money(v.amount)}</option>`).join('');
    if(!$('v1SettleDate').value)$('v1SettleDate').value=today();
    if ($('v1PoolCash') !== document.activeElement) $('v1PoolCash').value = cash.toFixed(2);
    if ($('v1Receivable') !== document.activeElement) $('v1Receivable').value = receivable.toFixed(2);
    const body = $('v1PoolBody');
    if (p.broken) { body.textContent='账本数据异常，已停止计算，请先导出原始数据检查。';return null; }
    if (!latest) { body.innerHTML = '<div class="v1-warn">请先录入总金融资产。</div>'; return null; }
    const b = C.poolBudget(latest.total_assets, poolValue, 0, p.ratio || 0.10);
    const cls = b.over_target > 0 ? 'v1-warn' : '';
    body.innerHTML = `
      <table class="v1-table"><tbody>
        <tr><td>总金融资产</td><td class="v1-num">${money(b.total_assets)}</td><td class="v1-mini">${esc(latest.date)}</td></tr>
        <tr><td>资金池目标（${(b.ratio * 100).toFixed(0)}%）</td><td class="v1-num">${money(b.pool_target)}</td><td></td></tr>
        <tr><td>当前池子</td><td class="v1-num">${money(b.pool_value)}</td><td class="v1-mini">现金 ${money(cash)} + 冻结 ${money(Number(p.frozenCash||0))} + 持仓 ${money(v.total)} + 在途 ${money(receivable)}</td></tr>
        <tr><td>允许新增投入</td><td class="v1-num">${money(b.new_allowed)}</td><td class="v1-mini">受外部可用现金限制</td></tr>
      </tbody></table>
      <div class="${cls}">${b.over_target > 0 ? `资金池已超过目标 ${money(b.over_target)}：暂停新增投入，不强制卖出。` : '资金池未超额。'}</div>`;
    if (v.missing.length) body.innerHTML += `<div class="v1-warn">以下资产净值缺失，已按“待更新”处理：${v.missing.map(esc).join('、')}</div>`;
    if (cash < 0) body.innerHTML += `<div class="v1-warn">池内现金记录为负（${money(cash)}）：请按实际可用现金校正，系统不会用负现金生成买入建议。</div>`;
    return { latest, b, v, cash, receivable };
  }

  function renderPlan() {
    $('v1PlanBody').textContent = '策略未启用：本轮仅修复账本，不生成真实买卖建议。';
    $('v1PlanStatus').textContent = '真实手工账本与模拟账户分开，正式投资配置未切换。';
  }

  function renderReview() {
    $('v1ReviewBody').textContent = '旧版月初持仓收益算法已停用；真实账户盈亏待日度估值与现金流核对完成后接入。';
    $('v1ReviewStatus').textContent = '不以旧算法估算实际盈亏。';
  }

  function renderAll() {
    renderSnapshot();
    renderPositions();
    renderPool();
    renderPlan();
    renderReview();
  }

  // ---------------- 事件 ----------------
  const snapDate = $('v1SnapDate');
  snapDate.value = today();
  const latest = S.latestSnapshot();
  if (latest) $('v1SnapAmount').value = latest.total_assets;
  $('v1SnapSave').onclick = () => {
    try {
      S.addSnapshot($('v1SnapDate').value, Number($('v1SnapAmount').value), $('v1SnapNote').value);
      $('v1SnapStatus').textContent = '已保存总资产。';
      $('v1SnapStatus').className = 'v1-ok';
      renderAll();
    } catch (e) {
      $('v1SnapStatus').textContent = e.message;
      $('v1SnapStatus').className = 'v1-err';
    }
  };

  $('v1PoolSave').onclick = () => {
    try {
      const p = profile();
      if (Number($('v1Receivable').value)!==0) throw Error('在途须由逐笔确认赎回生成');
      const rows=[...document.querySelectorAll('#v1PositionsBody tr')];
      S.initializeLedger({date:today(),cash:Number($('v1PoolCash').value),positions:rows.map(tr=>({code:tr.dataset.code,shares:Number(tr.querySelector('.v1-shares').value)}))});
      $('v1PoolStatus').textContent = '已保存池内现金与在途资金。';
      $('v1PoolStatus').className = 'v1-ok';
      renderAll();
    } catch (e) {
      $('v1PoolStatus').textContent = e.message;
      $('v1PoolStatus').className = 'v1-err';
    }
  };

  $('v1Settle').onclick = () => {
    try {
      const id=$('v1SettleTrade').value;
      const amt=profile().payments?.[id]?.amount||0;
      S.settleTrade(id,$('v1SettleDate').value);
      $('v1PoolStatus').textContent = `已将 ${money(amt)} 赎回款从在途转入池内现金。`;
      $('v1PoolStatus').className = 'v1-ok';
      renderAll();
    } catch (e) {
      $('v1PoolStatus').textContent = e.message;
      $('v1PoolStatus').className = 'v1-err';
    }
  };

  $('v1PosSave').onclick = () => {
    try {
      const rows = [...document.querySelectorAll('#v1PositionsBody tr')];
      const list = rows.map(tr => ({
        code: tr.dataset.code,
        name: D.funds[tr.dataset.code] ? D.funds[tr.dataset.code].name : tr.dataset.code,
        shares: Number(tr.querySelector('.v1-shares').value) || 0
      }));
      const p = profile();
      if (!p.initialDate) S.initializeLedger({date:today(),cash:Number($('v1PoolCash').value),positions:list});
      else list.forEach(x => S.setShares(x.code, x.shares));
      $('v1PosStatus').textContent = '已保存份额。之后的成交会从投资日记自动更新。';
      $('v1PosStatus').className = 'v1-ok';
      renderAll();
    } catch (e) {
      $('v1PosStatus').textContent = e.message;
      $('v1PosStatus').className = 'v1-err';
    }
  };

  $('v1PosRebuild').onclick = () => {
    try {
      S.rebuildFromDiary(diary());
      $('v1PosStatus').textContent = '已按初始份额 + 日记成交重建持仓。';
      $('v1PosStatus').className = 'v1-ok';
      renderAll();
    } catch (e) {
      $('v1PosStatus').textContent = e.message;
      $('v1PosStatus').className = 'v1-err';
    }
  };

  $('v1ReviewMonth').onchange = renderReview;
  window.addEventListener('investment-diary-changed', () => { syncFromDiary(); renderAll(); });

  // 只读调试入口，便于自检与问题定位；不提供任何下单能力。
  window.XingxunV1 = { renderAll, status: S.status };

  syncFromDiary();
  renderAll();
})();
