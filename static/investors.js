(function () {
  const container = document.getElementById('investor-cards');
  if (!container) return;
  const titles = {ackman: '阿克曼', zhu: '朱少醒', berkshire: '伯克希尔'};
  const aliases = {'UBER TECHNOLOGIES INC':'优步','AMAZON COM INC':'亚马逊','MICROSOFT CORP':'微软','META PLATFORMS INC':'Meta','BROOKFIELD CORP':'Brookfield','RESTAURANT BRANDS INTL INC':'餐饮品牌国际','NETFLIX INC.':'奈飞','ALPHABET INC':'谷歌','APPLE INC':'苹果','OCCIDENTAL PETE CORP DEL':'西方石油','CHEVRON CORP NEW':'雪佛龙','CHUBB LIMITED':'安达保险','BANK AMERICA CORP':'美国银行','COCA COLA CO':'可口可乐','KRAFT HEINZ CO':'卡夫亨氏','MOODYS CORP':'穆迪','AMERICAN EXPRESS CO':'美国运通'};
  function make(tag, text, cls) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; }
  function appendGroup(card, heading, rows, cls) {
    const group = make('div', undefined, 'investor-group'); group.append(make('h4', heading));
    if (!rows.length) group.append(make('div', '本期没有可比较的变化', 'investor-empty'));
    rows.forEach(item => { const row = make('div', undefined, 'investor-row'); const name = aliases[item.name] || item.name; row.append(make('span', name, 'investor-row-name')); row.append(make('span', (item.pct > 0 ? '+' : '') + item.pct.toFixed(1) + '%', 'investor-row-change ' + cls)); group.append(row); });
    card.append(group);
  }
  Promise.resolve(window.INVESTOR_DATA).then(data => {
    container.replaceChildren();
    ['berkshire', 'zhu'].forEach(key => {
      const info = data[key]; const card = make('article', undefined, 'investor-card'); const head = make('div', undefined, 'investor-card-head');
      head.append(make('h3', titles[key])); head.append(make('span', '报告期 ' + info.period, 'investor-date')); card.append(head);
      // Only compare the same disclosed security across both quarters. A 13F option is not stock.
      const comparable = info.rows.filter(r => !r.option && r.unit !== 'PRN' && Number.isFinite(r.current) && Number.isFinite(r.previous) && r.previous > 0 && r.current !== r.previous).map(r => ({...r, pct: (r.current / r.previous - 1) * 100}));
      const increases = comparable.filter(r => r.pct > 0).sort((a, b) => b.pct - a.pct).slice(0, 3);
      const decreases = comparable.filter(r => r.pct < 0).sort((a, b) => a.pct - b.pct).slice(0, 3);
      const groups = make('div', undefined, 'investor-groups'); appendGroup(groups, '持股增加', increases, 'investor-up'); appendGroup(groups, '持股减少', decreases, 'investor-down'); card.append(groups);
      const source = make('p', undefined, 'investor-source'); source.append('按持股数量变化比例排列 · 披露 '); const link = make('a', info.disclosures[info.disclosures.length - 1].date); link.href = info.disclosures[info.disclosures.length - 1].url; link.target = '_blank'; link.rel = 'noopener noreferrer'; source.append(link); if (key === 'zhu') source.append(' · 股数为约数'); card.append(source); const research = document.getElementById('investor-research-' + key); if (research) card.append(research.content.cloneNode(true)); container.append(card);
    });
  }).catch(() => { container.replaceChildren(make('p', '暂时无法读取持仓数据，请稍后再试。', 'investor-loading')); });
}());
