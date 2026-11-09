const fs=require('fs'),vm=require('vm'),assert=require('assert');
let code=fs.readFileSync('templates/_status_rail.html','utf8')
  .replace(/^<script>\s*/,'').replace(/\s*<\/script>\s*$/,'')
  .replace('{{ asset_state_catalog | tojson }}','{}').replace('{{ asset_state_map | tojson }}','{}');
const context={document:{addEventListener(){},getElementById(){return null}},setInterval(){},localStorage:{getItem(){return null}}};
context.window=context;vm.createContext(context);vm.runInContext(code,context);
context.ASSET_STATE_CATALOG={sector_etf:[['watch','观察','blue','保持观察']]};
context.ASSET_DISPLAY_STATUS_MAP={};
const summary={asset_type:'sector_etf',status:'watch',action:'观察',reason:'行情更新受限，先观察',
  details:{data_warning:'更新失败'},decision_basis:[['行情前提','更新受限'],['PE分位','数据不足或过旧'],['价格','100']]};
const rail=context.assetStateRail(summary),basis=context.assetStrategyBasis(summary);
assert(rail.includes('当前建议：观察'));
assert(rail.includes('暂时观察。'));
assert(!rail.includes('更新受限'));
assert(!basis.includes('更新受限'));
assert(!basis.includes('过旧'));
assert(basis.includes('PE分位')&&basis.includes('暂无')&&basis.includes('100'));
assert.equal(summary.details.data_warning,'更新失败');
console.log('update notice display: ok');
