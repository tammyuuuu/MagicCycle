/* User-provided Alipay subscription rates, separate from research fee assumptions. */
(function(){
 const rates=Object.freeze({'008701':0.06,'000015':0.08,'161130':0.12}),asOf='2026-10-22';
 function forCode(code){return rates[code]==null?null:{code,channel:'alipay',buy_pct:rates[code],as_of:asOf,source:'user_provided'};}
 function forTrade(trade){
  const saved=trade.purchaseFeePolicy;if(saved?.code===trade.code&&saved.channel==='alipay'&&Number.isFinite(saved.buy_pct)&&saved.buy_pct>=0&&saved.buy_pct<=100)return saved;
  if(trade.productChannel&&trade.productChannel!=='alipay')return null;
  if((trade.submittedDate||trade.date||'')<asOf)return null;
  return forCode(trade.code);
 }
 function amount(gross,policy){return Math.round((gross-gross/(1+policy.buy_pct/100))*100)/100;}
 window.UserPurchaseFees={forCode,forTrade,amount};
})();
