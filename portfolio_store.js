/* 星循 V1：总资产快照、持仓与现金流（localStorage）。只存用户数据，不含行情。 */
(function () {
  let context = { mode: 'real', accountId: 'manual' };
  let PROFILE_KEY = 'xingxun_ledger_v2_real_manual';
  let SNAP_KEY = 'xingxun_snapshots_v2_real_manual';
  const DEFAULT_PROFILE = {
    version: 2, ratio: 0.10, mode: 'real', accountId: 'manual', entries: [], settlements: [], incomes: [],
    allocationId: null,
    poolCash: 0, positions: [], flows: [], updatedAt: null
  };
  let storageError = null;

  const isDate = v => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v);
  const isCode = v => typeof v === 'string' && /^\d{6}$/.test(v);
  const num = v => (typeof v === 'number' && Number.isFinite(v) ? v : null);

  function readRaw(key) {
    try { return localStorage.getItem(key); } catch (e) { storageError='浏览器存储无法读取，已停止写入'; throw Error(storageError); }
  }
  function writeRaw(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); return true; }
    catch (e) { storageError = '浏览器存储不可用或空间不足'; return false; }
  }

  function validateProfile(p) {
    if (!p || typeof p !== 'object') throw Error('档案格式错误');
    if (num(p.ratio) === null || p.ratio < 0 || p.ratio > 1) throw Error('预算比例无效');
    if (!Array.isArray(p.positions) || !Array.isArray(p.flows)) throw Error('持仓或流水格式错误');
    p.positions.forEach(x => {
      if (!isCode(String(x.code)) || num(x.shares) === null || x.shares < 0) throw Error('持仓格式错误');
    });
    p.flows.forEach(x => {
      if (!isDate(x.date) || !['deposit', 'withdraw'].includes(x.type) || num(x.amount) === null || x.amount <= 0) {
        throw Error('资金流水格式错误');
      }
    });
    for(const field of ['productChoices','productMappings','productTerms','productData'])if(p[field]!=null&&(typeof p[field]!=='object'||Array.isArray(p[field])))throw Error('产品配置格式错误');
    for(const [asset,code] of Object.entries(p.productChoices||{}))if(!/^[a-z0-9_-]+$/.test(asset)||!isCode(code))throw Error('产品选择无效');
    for(const [code,f] of Object.entries(p.productData||{})){if(!isCode(code)||!Array.isArray(f.nav))throw Error('产品净值数据无效');for(const point of f.nav)if(!Array.isArray(point)||!validDate(point[0])||point[0]>todayCN()||!Number.isFinite(point[1])||point[1]<=0)throw Error('产品净值日期或数值无效');}
    return p;
  }

  function profile() {
    const raw = readRaw(PROFILE_KEY);
    if (!raw) return { ...JSON.parse(JSON.stringify(DEFAULT_PROFILE)), ...context };
    try {
      const p = validateProfile(JSON.parse(raw));
      if (p.mode !== context.mode || p.accountId !== context.accountId) throw Error('账户错配');
      if (p.opening) Object.assign(p, replay(p));
      return p;
    } catch (e) {
      storageError = '已保存的档案格式异常，已停止计算（不会覆盖原数据）';
      const safe = JSON.parse(JSON.stringify(DEFAULT_PROFILE));
      safe.broken = true;
      return safe;
    }
  }

  function commitProfile(p, earlierStart = null) {
    validateProfile(p);
    if (p.mode !== context.mode || p.accountId !== context.accountId || p.broken) throw Error('账户不匹配或档案异常');
    const oldRaw = readRaw(PROFILE_KEY);
    if (oldRaw) {
      const old = JSON.parse(oldRaw);
      if (old.opening && JSON.stringify(old.opening) !== JSON.stringify(p.opening)) throw Error('期初基线已冻结');
      if(earlierStart!==null){dateOK(earlierStart);if(!old.opening||earlierStart>old.opening.date||earlierStart>todayCN())throw Error('历史起始日无效');p.opening={...old.opening,date:earlierStart};}
      const fields = ['opening','entries','journal','flows','settlements','incomes'];
      if (fields.some(k=>JSON.stringify(old[k])!==JSON.stringify(p[k]))) {
        p.revisions = [...(old.revisions || []), { savedAt:new Date().toISOString(), ...Object.fromEntries(fields.map(k=>[k,old[k]??null])) }];
      } else p.revisions = old.revisions || [];
    }
    if (p.opening) Object.assign(p, replay(p));
    p.updatedAt = new Date().toISOString();
    return writeRaw(PROFILE_KEY, p);
  }

  function saveProfile(p){return commitProfile(p);}
  // Commit a historical trade and its date-only baseline extension in one validated write.
  function saveHistoricalProfile(p,date){return commitProfile(p,date);}

  function snapshots() {
    const raw = readRaw(SNAP_KEY);
    if (!raw) return profile().restoredSnapshots || [];
    try {
      const list = JSON.parse(raw);
      if (!Array.isArray(list)) throw Error();
      list.forEach(s => {
        if (!validDate(s.date) || (context.mode==='real' && s.date>todayCN()) || num(s.total_assets) === null || s.total_assets < 0 || s.total_assets > 1e9) {
          throw Error();
        }
      });
      return list.sort((a, b) => a.date.localeCompare(b.date));
    } catch (e) {
      storageError = '总资产快照格式异常，已停止计算';
      return [];
    }
  }

  function latestSnapshot() {
    const list = snapshots();
    return list.length ? list[list.length - 1] : null;
  }

  function addSnapshot(date, total, note = '') {
    const value = Number(total);
    if (!validDate(date) || (context.mode==='real' && date>todayCN()) || !Number.isFinite(value) || value < 0 || value > 1e9) {
      throw Error('请输入有效的日期与总金融资产');
    }
    const list = snapshots().filter(s => s.date !== date);
    list.push({ date, total_assets: value, note: String(note || ''), confirmed_at: new Date().toISOString() });
    list.sort((a, b) => a.date.localeCompare(b.date));
    if (!writeRaw(SNAP_KEY, list)) throw Error(storageError || '保存失败');
    return list[list.length - 1];
  }

  const copy = x => JSON.parse(JSON.stringify(x));
  function newId() {
    if(typeof crypto.randomUUID==='function')return crypto.randomUUID();
    const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
    const h=[...bytes].map(x=>x.toString(16).padStart(2,'0')).join('');
    return h.slice(0,8)+'-'+h.slice(8,12)+'-'+h.slice(12,16)+'-'+h.slice(16,20)+'-'+h.slice(20);
  }
  const todayCN = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date());
  const validDate = x => isDate(x) && !Number.isNaN(Date.parse(x)) && new Date(x).toISOString().slice(0, 10) === x;
  function dateOK(x) { if (!validDate(x)) throw Error('日期无效'); }
  function positive(x, label) { if (!Number.isFinite(x) || x <= 0) throw Error(label + '必须大于0'); }
  function nonnegative(x, label) { if (!Number.isFinite(x) || x < 0) throw Error(label + '必须为非负有限数'); }
  function unique(rows) {
    const m = new Map();
    rows.forEach(e => {
      if (!e || typeof e.id !== 'string' || !e.id.trim()) throw Error('事件缺少唯一id');
      if (m.has(e.id) && JSON.stringify(m.get(e.id)) !== JSON.stringify(e)) throw Error('重复id内容冲突');
      m.set(e.id, e);
    });
    return [...m.values()];
  }
  const states = ['suggested', 'pending', 'submitted', 'confirmed', 'failed', 'cancelled'];
  function validateTrade(e) {
    if (!e || !states.includes(e.status) || !['买入','加仓','卖出','减仓'].includes(e.action) || !isCode(e.code)) throw Error('交易状态、方向或代码无效');
    dateOK(e.date); positive(e.amount, '支付/净回款金额');
    if (e.mode === 'real' && [e.date,e.submittedDate,e.confirmedDate,e.resolvedDate].filter(Boolean).some(x=>x>todayCN())) throw Error('真实记录不能使用未来日期');
    if (e.submittedDate) { dateOK(e.submittedDate); if (e.submittedDate < e.date) throw Error('提交日期早于订单日期'); }
    const sell = ['卖出','减仓'].includes(e.action);
    if(e.quantity != null) positive(e.quantity,'份额');
    if (sell || e.status === 'confirmed') positive(e.quantity, '实际/申请份额');
    if (e.status === 'confirmed') {
      dateOK(e.confirmedDate);
      if (e.confirmedDate < (e.submittedDate || e.date)) throw Error('确认早于提交');
      nonnegative(e.fee, '实际手续费');
      if(!sell && e.fee>=e.amount)throw Error('申购费不得达到支付总额');
      if (e.price != null) {
        positive(e.price, '确认净值');
        const expected = e.quantity * e.price + (sell ? -e.fee : e.fee);
        if (Math.abs(expected - e.amount) > 0.021) throw Error('金额、份额、净值和费用不一致');
      }
    }
    if (['failed','cancelled'].includes(e.status) && e.submittedDate) {
      dateOK(e.resolvedDate); if (e.resolvedDate < e.submittedDate) throw Error('撤销/失败早于提交');
    }
    return e;
  }

  /** Pure projection. Never uses current balances as a replay starting point. */
  function replay(p, asOf = todayCN()) {
    dateOK(asOf);
    if (!p.opening) throw Error('请先确认期初现金与份额；旧档案不会自动迁移');
    const b = p.opening; dateOK(b.date); nonnegative(b.cash, '期初现金');
    if(p.mode==='real' && b.date>todayCN())throw Error('期初不能在未来');
    const map = Object.create(null), frozenShares = Object.create(null), payments = Object.create(null), timeline = [];
    (b.positions || []).forEach(x => {
      if (!isCode(x.code) || map[x.code]) throw Error('期初代码无效或重复');
      nonnegative(x.shares, '期初份额'); map[x.code] = { ...copy(x), source: 'opening' };
    });
    if (asOf < b.date) return { poolCash: 0, frozenCash: 0, receivable: 0, positions: [], payments: {}, initialDate: b.date };
    let cash = b.cash, frozen = 0;
    const entries = unique(p.entries || []), settlements = unique(p.settlements || []), flows = unique(p.flows || []), incomes=unique(p.incomes||[]);
    unique([...entries, ...settlements, ...flows,...incomes]);
    const trades = new Map();
    const push = (date, order, id, fn) => timeline.push({ date, order, id, fn });
    flows.forEach(f => {
      dateOK(f.date); positive(f.amount, '资金流水');
      if(p.mode==='real' && f.date>todayCN())throw Error('流水不能在未来');
      if (!['deposit','withdraw'].includes(f.type) || f.date < b.date) throw Error('流水日期或类型无效');
      push(f.date, 0, f.id, () => { cash += (f.type === 'deposit' ? 1 : -1) * f.amount; });
    });
    incomes.forEach(e=>{
      dateOK(e.date);dateOK(e.exDate);positive(e.amount,'分红确认金额');
      if(!isCode(e.code)||e.exDate>e.date||e.date<b.date||!['cash','reinvest'].includes(e.kind))throw Error('分红记录无效');
      if(p.mode==='real'&&e.date>todayCN())throw Error('分红确认不能在未来');
      if(e.kind==='reinvest')positive(e.quantity,'红利再投资确认份额');
      push(e.date,0,e.id,()=>{
        if(e.kind==='cash')cash+=e.amount;
        else {if(!map[e.code])map[e.code]={code:e.code,name:e.code,shares:0,cost:0,source:'dividend'};map[e.code].shares+=e.quantity;}
      });
    });
    entries.forEach(e => {
      validateTrade(e);
      if (e.mode !== p.mode || e.accountId !== p.accountId) throw Error('交易账户不匹配');
      if (e.date < b.date) throw Error('交易早于期初');
      trades.set(e.id, e);
      if (['suggested','pending'].includes(e.status)) return;
      const sell = ['卖出','减仓'].includes(e.action);
      const submitted = e.submittedDate || (['submitted','confirmed'].includes(e.status) ? e.date : null);
      if (!submitted) return;
      push(submitted, 2, e.id, () => {
        if (sell) {
          if ((map[e.code]?.shares || 0) - (frozenShares[e.code] || 0) + 1e-9 < e.quantity) throw Error('卖出超过可用份额');
          frozenShares[e.code] = (frozenShares[e.code] || 0) + e.quantity;
        } else { cash -= e.amount; frozen += e.amount; }
      });
      if (e.status === 'confirmed') push(e.confirmedDate, 3, e.id, () => {
        if (sell) {
          map[e.code].shares -= e.quantity; frozenShares[e.code] -= e.quantity;
          payments[e.id] = { amount: e.amount, date: e.confirmedDate, settled: false };
        } else {
          frozen -= e.amount;
          if (!map[e.code]) map[e.code] = { code: e.code, name: e.name || e.code, shares: 0, cost: 0, source: 'confirmed' };
          map[e.code].shares += e.quantity; map[e.code].cost = (map[e.code].cost || 0) + e.amount;
        }
      });
      if (['failed','cancelled'].includes(e.status)) push(e.resolvedDate, 3, e.id, () => {
        if (sell) frozenShares[e.code] -= e.quantity;
        else { frozen -= e.amount; cash += e.amount; }
      });
    });
    settlements.forEach(s => {
      dateOK(s.date); positive(s.amount, '到账金额');
      if(p.mode==='real' && s.date>todayCN())throw Error('到账不能在未来');
      const e = trades.get(s.tradeId);
      if (!e || e.status !== 'confirmed' || !['卖出','减仓'].includes(e.action) || s.date < e.confirmedDate || Math.abs(s.amount-e.amount)>1e-8) throw Error('到账记录与赎回不匹配');
      push(s.date, 4, s.id, () => {
        // Same-day confirmation must precede settlement, but settlement precedes new orders.
        const payment = payments[s.tradeId];
        if (!payment || payment.settled) throw Error('赎回尚未确认或重复到账');
        payment.settled = true; cash += s.amount;
      });
    });
    timeline.sort((a,b) => a.date.localeCompare(b.date) || a.order-b.order || a.id.localeCompare(b.id));
    // A same-day redemption settlement cannot fund orders before its confirmation.
    timeline.forEach(e => { if (e.date <= asOf) { e.fn(); if (cash < -1e-8 || frozen < -1e-8) throw Error('账本现金不足或事件顺序错误'); } });
    return { poolCash: Math.max(0,cash), frozenCash: Math.max(0,frozen),
      receivable: Object.values(payments).filter(x=>!x.settled).reduce((a,x)=>a+x.amount,0),
      positions: Object.values(map).filter(x=>x.shares>1e-9).map(x=>({...x, availableShares:x.shares-(frozenShares[x.code]||0)})),
      payments, initialDate: b.date, initialPositions: copy(b.positions || []) };
  }

  // Explicit date-only extension; ordinary saves still cannot alter frozen opening balances.
  function extendLedgerStart(date) {
    dateOK(date);const p=profile();if(p.broken||!p.opening)throw Error('请先初始化有效账本');
    if(date>p.opening.date)throw Error('起始日只能提前，不能截掉已有历史');
    if(date===p.opening.date)return p;
    const original=copy(p.opening),fields=['opening','entries','journal','flows','settlements','incomes'];
    p.revisions=[...(p.revisions||[]),{savedAt:new Date().toISOString(),reason:'extend_ledger_start',...Object.fromEntries(fields.map(k=>[k,copy(p[k]??null)]))}];
    p.opening={...original,date};Object.assign(p,replay(p));p.updatedAt=new Date().toISOString();
    if(!writeRaw(PROFILE_KEY,p))throw Error(storageError);return profile();
  }

  function initializeLedger({ date, cash, positions = [] }) {
    const p = profile();
    if (p.opening || (p.entries || []).length) throw Error('期初已冻结，不能覆盖');
    p.opening = { date, cash, positions: copy(positions) }; p.entries=[]; p.settlements=[]; p.flows=[];
    if (!saveProfile(p)) throw Error(storageError); return profile();
  }
  function addFlow(date, type, amount, note = '', id) {
    const p = profile();
    if(!p.opening)throw Error('请先确认期初');
    p.flows = [...p.flows, { id: id || 'flow-' + newId(), date, type, amount, note }];
    if (!saveProfile(p)) throw Error(storageError); return profile();
  }
  function setInitialPositions(list, date) {
    return initializeLedger({ date: date || todayCN(), cash: profile().poolCash || 0, positions: list }).positions;
  }
  function applyNewEntries(entries) {
    const p = profile();
    if (p.broken || !p.opening) return p;
    // Unscoped v1 diary is history, never implicitly imported into a new ledger.
    p.journal = copy(unique(entries.filter(e => e.mode === p.mode && e.accountId === p.accountId)));
    p.entries = p.journal.filter(e=>e.action!=='观察');
    reconcileSettlements(p);
    if (!saveProfile(p)) throw Error(storageError); return profile();
  }
  function rebuildFromDiary(entries) { return applyNewEntries(entries).positions; }
  function settleTrade(tradeId, date, id) {
    const p = profile(); const e = (p.entries || []).find(x=>x.id===tradeId);
    if (!e) throw Error('找不到赎回');
    p.settlements = [...(p.settlements || []), { id: id || 'settle-' + tradeId, tradeId, date, amount: e.amount }];
    if (!saveProfile(p)) throw Error(storageError); return profile();
  }
  function clearReceivable() { throw Error('请逐笔提供赎回订单与实际到账日期，禁止整池自动到账'); }
  function addIncome(e) {
    const p=profile();if(!p.opening)throw Error('请先确认期初');
    p.incomes=[...(p.incomes||[]),copy(e)];if(!saveProfile(p))throw Error(storageError);return profile();
  }
  function removeFlow(id) {
    const p=profile();p.flows=p.flows.filter(f=>f.id!==id);if(!saveProfile(p))throw Error(storageError);return profile();
  }
  function removeIncome(id) {
    const p=profile();p.incomes=(p.incomes||[]).filter(e=>e.id!==id);if(!saveProfile(p))throw Error(storageError);return profile();
  }
  function setShares() { throw Error('期初冻结后请更正原交易记录，不可直接覆盖份额'); }
  function sharesFromDiary(entries, initial, asOf) {
    return replay({ ...profile(), opening:{date:'1900-01-01',cash:1e12,positions:initial||[]}, entries, flows:[], settlements:[] },asOf||todayCN()).positions;
  }
  function setContext(mode, accountId) {
    if (!['real','simulation'].includes(mode) || !/^[a-zA-Z0-9_-]{1,40}$/.test(accountId)) throw Error('账户类型或id无效，历史回测不能写交易账本');
    context={mode,accountId}; PROFILE_KEY='xingxun_ledger_v2_'+mode+'_'+accountId; SNAP_KEY='xingxun_snapshots_v2_'+mode+'_'+accountId;
    return profile();
  }
  function legacyProfile() { const raw=readRaw('xingxun_profile_v1'); return raw ? JSON.parse(raw) : null; }
  function journal() { return copy(profile().journal || []); }
  function reconcileSettlements(p) {
    const funded=new Set((p.entries||[]).filter(e=>['submitted','confirmed'].includes(e.status)).map(e=>e.id));p.flows=(p.flows||[]).filter(f=>f.source!=='actual_trade_payment'||funded.has(f.tradeId));
    const sales=new Map((p.entries||[]).filter(e=>e.status==='confirmed' && ['卖出','减仓'].includes(e.action)).map(e=>[e.id,e]));
    // A correction/deletion reverses the complete transaction, including its
    // linked payout. Prior source records remain in revisions.
    p.settlements=(p.settlements||[]).filter(s=>sales.has(s.tradeId)).map(s=>({...s,amount:sales.get(s.tradeId).amount}));
  }
  function saveJournal(entries) {
    const p=profile(); if(p.broken) throw Error('档案异常');
    entries=unique(entries);
    if(entries.some(e=>e.mode!==p.mode || e.accountId!==p.accountId)) throw Error('禁止混合真实、模拟或历史记录');
    const own=entries.filter(e=>e.mode===p.mode && e.accountId===p.accountId && e.action!=='观察');
    if (own.length && !p.opening) throw Error('请先确认账本期初现金与份额');
    p.journal=copy(entries); p.entries=copy(own);
    reconcileSettlements(p);
    if (!saveProfile(p)) throw Error(storageError); return journal();
  }
  function transitionTrade(id, status, changes = {}) {
    const rows=journal(), old=rows.find(e=>e.id===id);
    const allowed={suggested:['pending','cancelled'],pending:['submitted','cancelled'],submitted:['confirmed','failed','cancelled'],confirmed:[],failed:[],cancelled:[]};
    if (!old || !allowed[old.status]?.includes(status)) throw Error('非法状态转换');
    return saveJournal(rows.map(e=>e.id===id ? {...e,...changes,submittedDate:e.submittedDate || (e.status==='submitted'?e.date:changes.submittedDate),id,status} : e));
  }
  function exportBackup() {
    const p=profile();
    if(p.broken)return {schema:'xingxun-ledger-recovery-v2',...context,rawProfile:readRaw(PROFILE_KEY),rawSnapshots:readRaw(SNAP_KEY)};
    return copy({schema:'xingxun-ledger-v2',mode:context.mode,accountId:context.accountId,profile:p,snapshots:snapshots()});
  }
  function restoreBackup(bundle) {
    if(bundle?.schema!=='xingxun-ledger-v2' || bundle.mode!==context.mode || bundle.accountId!==context.accountId) throw Error('备份类型或账户不匹配');
    const current=profile(); if(current.opening || (current.journal||[]).length || snapshots().length) throw Error('只允许恢复到空账户，禁止覆盖现有账本');
    const p=copy(bundle.profile);validateProfile(p);
    if(p.mode!==context.mode || p.accountId!==context.accountId)throw Error('备份账户错配');
    const own=(p.journal||[]).filter(e=>e.action!=='观察');
    if(JSON.stringify(own)!==JSON.stringify(p.entries||[]))throw Error('备份日记与交易源不一致');
    if(p.opening)replay(p);
    if(!Array.isArray(bundle.snapshots) || bundle.snapshots.some(s=>!validDate(s.date)||(context.mode==='real'&&s.date>todayCN())||!Number.isFinite(s.total_assets)||s.total_assets<0||s.total_assets>1e9))throw Error('备份快照无效');
    // Single envelope is authoritative; snapshots are included in the same write.
    p.restoredSnapshots=copy(bundle.snapshots);
    if(!saveProfile(p))throw Error(storageError);return profile();
  }

  /** 用最新净值计算市值；缺净值的资产返回 missing，不用旧净值替代。 */
  function valuePositions(positions, funds) {
    let total = 0;
    const missing = [];
    const rows = (positions || []).map(p => {
      const f = (funds || {})[p.code];
      const nav = f && Number.isFinite(f.nav) ? f.nav : null;
      const navOk = nav !== null && f.nav_date;
      const value = navOk ? p.shares * nav : null;
      if (!navOk) missing.push(p.code);
      else total += value;
      return { ...p, nav, nav_date: f ? f.nav_date : null, value, priced: navOk };
    });
    return { rows, total, missing };
  }

  function status() {
    return { error: storageError, profile: profile(), latest: latestSnapshot() };
  }

  window.XingxunStore = {
    get PROFILE_KEY() { return PROFILE_KEY; }, get SNAP_KEY() { return SNAP_KEY; }, DEFAULT_PROFILE,
    replay, initializeLedger, extendLedgerStart, settleTrade, setContext, legacyProfile, validateTrade,
    journal, saveJournal, transitionTrade, exportBackup, restoreBackup, addIncome, removeFlow, removeIncome, newId,
    profile, saveProfile, saveHistoricalProfile, snapshots, latestSnapshot, addSnapshot,
    addFlow, setInitialPositions, applyNewEntries, rebuildFromDiary,
    setShares, sharesFromDiary, valuePositions, status,
    clearReceivable
  };
})();
