const fs=require('fs'),vm=require('vm'),path=require('path');
const root=path.resolve(__dirname,'..');
let store={};const ctx={window:{},localStorage:{getItem:k=>store[k]??null,setItem:(k,v)=>store[k]=v},console};
vm.createContext(ctx);
for(const f of ['portfolio_store.js','capital_pool.js'])vm.runInContext(fs.readFileSync(path.join(root,f),'utf8'),ctx);
const S=ctx.window.XingxunStore,C=ctx.window.CapitalPool;
function reset(){store={};S.setInitialPositions([],'2026-10-01');const p=S.profile();p.poolCash=2000;S.saveProfile(p);}
let out={};reset();const buy={id:'buy1',date:'2026-10-02',code:'000015',action:'买入',amount:1000,quantity:1000,price:1};
S.applyNewEntries([buy]);out.afterBuy=S.profile().poolCash;S.rebuildFromDiary([buy]);out.afterRebuild=S.profile().poolCash;S.rebuildFromDiary([buy]);out.afterSecondRebuild=S.profile().poolCash;
reset();S.applyNewEntries([buy]);S.applyNewEntries([]);out.deletedDiaryStillHeld=S.profile().positions;
reset();S.applyNewEntries([{...buy,quantity:null,amount:1000,price:1}]);out.noConfirmedQuantity=S.profile();
reset();S.applyNewEntries([{...buy,action:'卖出',quantity:1000}]);out.sellWithoutHoldings=S.profile();
const fund={name:'test',nav:1,status:'开放申购',buy_pct:.08,redeem_tiers:[{condition:'小于7天',original_pct:1.5},{condition:'大于等于7天',original_pct:0}],limit:'5元/日'};
out.belowMinimumAfterLimit=C.planDay({totalAssets:20000,poolCash:2000,targets:{'000015':1},funds:{'000015':fund}}).rows;
out.pausedSubscriptionBlocksSell=C.planDay({totalAssets:20000,poolCash:0,positions:[{code:'000015',value:2000,holdDays:365}],targets:{'000015':0},funds:{'000015':{...fund,status:'暂停申购'}}}).rows;
fs.writeFileSync(path.join(__dirname,'site_evidence.json'),JSON.stringify(out,null,2));console.log(JSON.stringify(out,null,2));
