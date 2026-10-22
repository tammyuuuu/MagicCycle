/* Shared display labels only; research identifiers and data stay unchanged. */
(function(){
 const names=Object.freeze({A:'纳指等权',B:'纳指均衡',C:'纳指稳健',D:'标普等权',E:'标普均衡',F:'标普稳健',L1:'债券＋黄金',L2:'债券＋黄金＋红利',L3:'债券＋黄金＋中证500',L4:'债券＋黄金＋沪深300'});
 const ids=Object.freeze(Object.keys(names));
 const label=id=>names[id]?id+' · '+names[id]:String(id||'未选择');
 window.StrategyLabels=Object.freeze({names,ids,label});
})();
