(function () {
  const node = document.getElementById('dash-data');
  if (!node || typeof Chart === 'undefined') return;
  const payload = JSON.parse(node.textContent);
  const byRange = payload.byRange || { all: payload };

  const fa = (n) => new Intl.NumberFormat('fa-IR').format(Math.round(Number(n) || 0));
  function moneyUnit() {
    const match = document.cookie.match(/(?:^|; )money_unit=([^;]*)/);
    const unit = match ? decodeURIComponent(match[1]) : 'auto';
    return unit === 'million' || unit === 'billion' ? unit : 'auto';
  }
  function countText(n) {
    return fa(n) + ' فاکتور';
  }
  function moneyText(n, scale) {
    const raw = Number(n);
    if (!Number.isFinite(raw)) return '۰';
    let div = 1;
    let name = 'تومان';
    if (scale && scale.div) {
      div = scale.div;
      name = scale.name || 'تومان';
    } else {
      const abs = Math.abs(raw);
      let chosen = moneyUnit();
      if (chosen === 'auto') {
        if (abs >= 1e9) chosen = 'billion';
        else if (abs >= 1e6) chosen = 'million';
        else chosen = 'toman';
      }
      if (chosen === 'billion') {
        div = 1e9;
        name = 'میلیارد';
      } else if (chosen === 'million') {
        div = 1e6;
        name = 'میلیون';
      }
    }
    if (div === 1) return fa(raw) + ' تومان';
    const scaled = raw / div;
    const absScaled = Math.abs(scaled);
    const digits = absScaled >= 100 ? 1 : absScaled >= 1 ? 2 : absScaled >= 0.01 ? 3 : absScaled >= 0.001 ? 4 : 6;
    const text = scaled.toLocaleString('fa-IR', { maximumFractionDigits: digits, minimumFractionDigits: 0 });
    return text + ' ' + name;
  }
  Chart.defaults.font.family = 'Vazirmatn, sans-serif';
  Chart.defaults.color = '#64748b';
  Chart.defaults.plugins.legend.rtl = true;
  Chart.defaults.plugins.legend.labels.font = { family: 'Vazirmatn', weight: '700' };

  function valueOf(ctx) {
    const parsed = ctx.parsed;
    if (parsed && typeof parsed === 'object') {
      if (ctx.chart.options.indexAxis === 'y') return parsed.x;
      if (parsed.y != null) return parsed.y;
    }
    return parsed;
  }

  function tip(kind, named) {
    return {
      callbacks: {
        label: (ctx) => {
          const n = fa(valueOf(ctx));
          const name = named && ctx.dataset && ctx.dataset.label ? ctx.dataset.label + ' ' : '';
          if (kind === 'pct') return ' ' + name + n + '٪';
          if (kind === 'count') return ' ' + name + n;
          return ' ' + name + moneyText(valueOf(ctx));
        },
      },
    };
  }

  const grid = { color: '#e2e8f0' };

  function datasetValues(datasets) {
    return (datasets || []).flatMap((dataset) => dataset.data || []);
  }

  function moneyTicks(values) {
    const scale = moneyScale(values);
    return {
      stepSize: scale.step,
      callback: (value) => {
        if (!scale.name) return fa(value);
        const text = (Number(value) / scale.div).toLocaleString('fa-IR', { maximumFractionDigits: 2 });
        return text + ' ' + scale.name;
      },
    };
  }

  function bar(labels, datasets, horizontal, kind, xTicks) {
    if (!labels || !labels.length) return null;
    const valueTicks = kind === 'pct' || kind === 'count' ? { callback: (v) => fa(v) } : moneyTicks(datasetValues(datasets));
    return {
      type: 'bar',
      data: { labels, datasets },
      options: {
        indexAxis: horizontal ? 'y' : 'x',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { tooltip: tip(kind) },
        scales: {
          x: { grid, ticks: horizontal ? valueTicks : (xTicks || categoryTicks()) },
          y: { grid, ticks: horizontal ? categoryTicks() : valueTicks },
        },
      },
    };
  }

  function categoryTicks() {
    return {
      autoSkip: false,
      color: '#334155',
      font: { family: 'Vazirmatn', size: 12, weight: '700' },
      callback(value) {
        return this.getLabelForValue(value);
      },
    };
  }

  function moneyScale(values) {
    const max = Math.max(0, ...(values || []).map((n) => Math.abs(Number(n) || 0)));
    let chosen = moneyUnit();
    if (chosen === 'auto') {
      if (max >= 1e9) chosen = 'billion';
      else if (max >= 1e6) chosen = 'million';
      else chosen = 'toman';
    }
    if (chosen === 'toman') return { div: 1, name: '', step: undefined };
    const div = chosen === 'billion' ? 1e9 : 1e6;
    const name = chosen === 'billion' ? 'میلیارد' : 'میلیون';
    const scaled = max / div;
    let stepUnits = 1;
    if (scaled <= 0.2) stepUnits = 0.05;
    else if (scaled <= 0.5) stepUnits = 0.1;
    else if (scaled <= 1) stepUnits = 0.2;
    else if (scaled <= 2) stepUnits = 0.5;
    else if (scaled <= 5) stepUnits = 1;
    else if (scaled <= 20) stepUnits = 5;
    else if (scaled <= 100) stepUnits = 10;
    else if (scaled <= 200) stepUnits = 20;
    else if (scaled <= 500) stepUnits = 50;
    else stepUnits = 100;
    return { div, name, step: stepUnits * div };
  }

  function drawnPoints(points) {
    return (points || []).filter((point) => point && !point.skip && Number.isFinite(point.x) && Number.isFinite(point.y));
  }

  function traceForward(ctx, points) {
    ctx.moveTo(points[0].x, points[0].y);
    for (let index = 1; index < points.length; index += 1) {
      const prev = points[index - 1];
      const point = points[index];
      ctx.bezierCurveTo(
        Number.isFinite(prev.cp2x) ? prev.cp2x : prev.x,
        Number.isFinite(prev.cp2y) ? prev.cp2y : prev.y,
        Number.isFinite(point.cp1x) ? point.cp1x : point.x,
        Number.isFinite(point.cp1y) ? point.cp1y : point.y,
        point.x,
        point.y,
      );
    }
  }

  function fillUnderCurve(ctx, points, floor, color) {
    ctx.beginPath();
    traceForward(ctx, points);
    ctx.lineTo(points[points.length - 1].x, floor);
    ctx.lineTo(points[0].x, floor);
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
  }

  function paintDottedSurface(chart) {
    const area = chart.chartArea;
    const axis = chart.scales.y;
    if (!area || !axis) return;
    const floor = axis.getPixelForValue(0);
    const ctx = chart.ctx;
    ctx.save();
    ctx.beginPath();
    ctx.rect(area.left, area.top, area.right - area.left, area.bottom - area.top);
    ctx.clip();
    chart.data.datasets.forEach((dataset, index) => {
      if (dataset.surface !== 'band') return;
      const meta = chart.getDatasetMeta(index);
      if (meta.hidden) return;
      const points = drawnPoints(meta.data);
      if (points.length < 2) return;
      fillUnderCurve(ctx, points, floor, dataset.surfaceColor);
    });
    ctx.restore();
  }

  function mergeBuyers(repeat, once) {
    const count = Math.max((repeat || []).length, (once || []).length);
    const months = [];
    for (let index = 0; index < count; index += 1) {
      const byId = new Map();
      [...((repeat || [])[index] || []), ...((once || [])[index] || [])].forEach((person) => {
        if (!person) return;
        const key = person.id != null ? person.id : person.name;
        const prev = byId.get(key);
        const amount = Number(person.amount) || 0;
        if (!prev) byId.set(key, { ...person, amount });
        else prev.amount += amount;
      });
      months.push([...byId.values()].sort((a, b) => (Number(b.amount) || 0) - (Number(a.amount) || 0)));
    }
    return months;
  }

  function areaTrend(labels, salesRepeat, salesOnce, profitRepeat, profitOnce, buyers) {
    if (!labels || !labels.length) return null;
    const people = buyers || {};
    const add = (left, right) => (left || []).map((n, index) => (Number(n) || 0) + (Number((right || [])[index]) || 0));
    const salesTotal = add(salesRepeat, salesOnce);
    const profitTotal = add(profitRepeat, profitOnce);
    const scale = moneyScale(salesTotal.concat(profitTotal));
    const line = (label, data, color, fill, stack, strong, customers) => ({
      label,
      data,
      customers: customers || [],
      stack,
      order: stack === 'profit' ? 0 : 1,
      borderColor: color,
      backgroundColor: strong ? color : fill,
      surface: strong ? 'base' : 'band',
      surfaceColor: strong ? color : fill,
      fill: false,
      tension: 0.35,
      cubicInterpolationMode: 'monotone',
      borderWidth: strong ? 3.5 : 2.5,
      borderDash: strong ? [1, 7] : undefined,
      borderCapStyle: strong ? 'round' : 'butt',
      pointRadius: stack === 'profit' ? 5 : 4,
      pointHoverRadius: 7,
      pointHitRadius: 16,
      pointBackgroundColor: color,
      pointBorderColor: '#fff',
      pointBorderWidth: 2,
      pointHoverBorderWidth: 2,
    });
    return {
      type: 'line',
      plugins: [{ id: 'dottedSurface', beforeDatasetsDraw: paintDottedSurface }],
      data: {
        labels,
        datasets: [
          line('فروش ثابت', salesRepeat, '#1c8eaa', 'rgba(28, 142, 170, 0.28)', 'sales', true, people.salesRepeat),
          line('فروش کل', salesTotal, '#7ec8db', 'rgba(126, 200, 219, 0.72)', 'sales', false, mergeBuyers(people.salesRepeat, people.salesOnce)),
          line('سود ثابت', profitRepeat, '#0f8f5f', 'rgba(21, 153, 106, 0.92)', 'profit', true, people.profitRepeat),
          line('سود کل', profitTotal, '#1aa36c', 'rgba(134, 214, 176, 0.42)', 'profit', false, mergeBuyers(people.profitRepeat, people.profitOnce)),
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            position: 'bottom',
            rtl: true,
            labels: {
              usePointStyle: true,
              pointStyle: 'line',
              boxWidth: 28,
              boxHeight: 6,
              padding: 18,
              color: '#64748b',
              font: { family: 'Vazirmatn', weight: '700', size: 13 },
            },
          },
          tooltip: tip(undefined, true),
        },
        scales: {
          x: {
            grid: { display: false },
            border: { display: false },
            ticks: {
              color: '#64748b',
              autoSkip: false,
              maxRotation: 0,
              font: { family: 'Vazirmatn', size: 12, weight: '700' },
            },
          },
          y: {
            position: 'right',
            stacked: false,
            beginAtZero: true,
            grace: '8%',
            grid: { color: '#e8eef2', drawTicks: false },
            border: { display: false },
            ticks: {
              color: '#64748b',
              padding: 10,
              stepSize: scale.step,
              font: { family: 'Vazirmatn', size: 12, weight: '600' },
              callback: (value) => {
                if (!scale.name) return fa(value);
                const text = (Number(value) / scale.div).toLocaleString('fa-IR', { maximumFractionDigits: 2 });
                return text + ' ' + scale.name;
              },
            },
          },
        },
      },
    };
  }

  function sharePercents(values) {
    const nums = values.map((n) => Number(n) || 0);
    const total = nums.reduce((sum, n) => sum + n, 0);
    if (!total) return nums.map(() => 0);
    const raw = nums.map((n) => (n / total) * 100);
    const whole = raw.map((n) => Math.floor(n));
    let left = 100 - whole.reduce((sum, n) => sum + n, 0);
    raw
      .map((n, index) => ({ index, rest: n - whole[index] }))
      .sort((a, b) => b.rest - a.rest)
      .slice(0, left)
      .forEach((item) => { whole[item.index] += 1; });
    return whole;
  }

  function hexToHsl(hex) {
    const raw = String(hex || '').replace('#', '');
    const full = raw.length === 3 ? raw.split('').map((ch) => ch + ch).join('') : raw;
    const n = parseInt(full, 16);
    if (!Number.isFinite(n) || full.length !== 6) return null;
    const r = ((n >> 16) & 255) / 255;
    const g = ((n >> 8) & 255) / 255;
    const b = (n & 255) / 255;
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const l = (max + min) / 2;
    const d = max - min;
    if (!d) return [0, 0, l];
    const s = d / (1 - Math.abs(2 * l - 1));
    let h = 0;
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    return [((h * 60) + 360) % 360, s, l];
  }

  function hslToHex(h, s, l) {
    const a = s * Math.min(l, 1 - l);
    const f = (n) => {
      const k = (n + h / 30) % 12;
      const channel = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
      return Math.round(255 * Math.min(1, Math.max(0, channel))).toString(16).padStart(2, '0');
    };
    return '#' + f(0) + f(8) + f(4);
  }

  function companion(hex) {
    const parsed = hexToHsl(hex);
    if (!parsed) return hex;
    const [h, s, l] = parsed;
    const nextL = l > 0.6 ? 0.38 : 0.64;
    const nextS = Math.max(0.72, Math.min(0.9, s || 0.78));
    return hslToHex(h, nextS, nextL);
  }

  function soften(hex) {
    const raw = String(hex || '').replace('#', '');
    const full = raw.length === 3 ? raw.split('').map((ch) => ch + ch).join('') : raw;
    const n = parseInt(full, 16);
    if (!Number.isFinite(n) || full.length !== 6) return hex;
    return 'rgba(' + ((n >> 16) & 255) + ', ' + ((n >> 8) & 255) + ', ' + (n & 255) + ', 0.45)';
  }

  const customerBase = String(payload.customerBase || '/customers/').replace(/\/?$/, '/');
  const salesBase = payload.salesBase ? String(payload.salesBase).replace(/\/?$/, '/') : '';

  function customerHref(id) {
    return customerBase + id + '/';
  }

  let openedCard = null;

  function customersPage() {
    return document.getElementById('chart-customers-page');
  }

  function placeCustomersPage() {
    const page = customersPage();
    const nav = document.querySelector('header.sticky');
    if (!page) return;
    page.style.top = (nav ? nav.offsetHeight : 0) + 'px';
  }

  function hideCustomers(card) {
    const page = customersPage();
    if (!page || page.hidden) return;
    if (card && openedCard && openedCard !== card) return;
    page.hidden = true;
    document.body.classList.remove('chart-customers-open');
    openedCard = null;
  }

  function showCustomers(card, title, people, key) {
    const page = customersPage();
    if (!page) return;
    people = Array.isArray(people) ? people : [];
    placeCustomersPage();
    openedCard = card;
    page.dataset.key = key;
    page.hidden = false;
    document.body.classList.add('chart-customers-open');
    const source = card && card.querySelector('h2');
    page.querySelector('[data-customers-source]').textContent = source ? source.textContent.trim() : '';
    page.querySelector('[data-customers-title]').textContent = title;
    const count = page.querySelector('[data-customers-count]');
    count.textContent = people.length ? fa(people.length) + ' مشتری' : 'بدون مشتری';
    const list = page.querySelector('[data-customers-list]');
    list.replaceChildren();
    if (!people.length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 3;
      cell.className = 'chart-customers-empty';
      cell.textContent = 'مشتری‌ای در این بخش نیست.';
      row.append(cell);
      list.append(row);
    } else {
      people.forEach((person, index) => {
        const row = document.createElement('tr');
        const rank = document.createElement('td');
        rank.textContent = fa(index + 1);
        const name = document.createElement('td');
        const link = document.createElement('a');
        link.href = customerHref(person.id);
        link.textContent = person.name || 'بدون نام';
        name.append(link);
        const amount = document.createElement('td');
        amount.className = 'amount';
        amount.dir = 'ltr';
        amount.textContent = moneyText(person.amount);
        row.append(rank, name, amount);
        list.append(row);
      });
    }
    page.scrollTop = 0;
    const back = page.querySelector('[data-customers-back]');
    if (back) back.focus();
  }

  function pieceButton(list, title, text, people) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'meta chart-piece';
    button.textContent = text;
    button.addEventListener('click', () => {
      showCustomers(list.closest('[data-chart]'), title, people || [], 'share:' + title);
    });
    return button;
  }

  function segmentTitle(chart, hit) {
    const category = (chart.data.labels || [])[hit.index] || '';
    if (chart.config.type === 'doughnut') {
      const kind = (hit.dataset.kinds || [])[hit.index] || '';
      return [category, kind].filter(Boolean).join(' · ');
    }
    return [hit.dataset.label, category].filter(Boolean).join(' · ');
  }

  function resolveTrendHit(chart, evt) {
    const area = chart.chartArea;
    const xScale = chart.scales.x;
    const yScale = chart.scales.y;
    if (!area || evt.x == null || evt.x < area.left || evt.x > area.right || evt.y < area.top || evt.y > area.bottom) return null;
    const index = Math.round(xScale.getValueForPixel(evt.x));
    const sets = chart.data.datasets || [];
    if (index < 0 || index >= (chart.data.labels || []).length || sets.length < 4) return null;
    const values = sets.map((dataset) => Number(dataset.data[index]) || 0);
    const lines = values
      .map((value, datasetIndex) => ({ datasetIndex, value, pixel: yScale.getPixelForValue(value) }))
      .filter((line) => line.value);
    lines.sort((a, b) => Math.abs(a.pixel - evt.y) - Math.abs(b.pixel - evt.y));
    let datasetIndex = null;
    if (lines.length && Math.abs(lines[0].pixel - evt.y) <= 14) datasetIndex = lines[0].datasetIndex;
    if (datasetIndex == null) {
      const yVal = Number(yScale.getValueForPixel(evt.y)) || 0;
      const salesTotal = values[1];
      const profitTotal = values[3];
      const tolerance = Math.max(salesTotal * 0.03, 1);
      if (profitTotal && yVal >= -tolerance && yVal <= profitTotal + tolerance) datasetIndex = 3;
      else if (salesTotal && yVal >= -tolerance && yVal <= salesTotal + tolerance) datasetIndex = 1;
    }
    if (datasetIndex == null) return null;
    const dataset = sets[datasetIndex];
    if (!dataset || !dataset.customers) return null;
    return { dataset, index, datasetIndex };
  }

  function resolveHit(chart, evt, elements) {
    if (chart.canvas.id === 'dailyChart') return resolveTrendHit(chart, evt);
    const el = elements && elements[0];
    if (!el) return null;
    const dataset = chart.data.datasets[el.datasetIndex];
    if (!dataset || !dataset.customers) return null;
    return { dataset, index: el.index, datasetIndex: el.datasetIndex };
  }

  function watchCursor(spec) {
    spec.options.onHover = (evt, elements, chart) => {
      chart.canvas.style.cursor = resolveHit(chart, evt, elements) ? 'pointer' : 'default';
    };
    spec.options.onClick = (evt, elements, chart) => {
      const hit = resolveHit(chart, evt, elements);
      const card = chart.canvas.closest('[data-chart]');
      if (!hit || !card) return;
      showCustomers(card, segmentTitle(chart, hit), hit.dataset.customers[hit.index] || [], hit.datasetIndex + ':' + hit.index);
      chart.setActiveElements([{ datasetIndex: hit.datasetIndex, index: hit.index }]);
      chart.update('none');
    };
  }

  function renderShare(canvas, loyalty) {
    const list = canvas.closest('[data-chart]')?.querySelector('[data-share]');
    if (!list || !loyalty) return;
    const labels = loyalty.labels || [];
    const values = loyalty.values || [];
    const colors = loyalty.colors || [];
    const repeat = loyalty.repeat;
    const once = loyalty.once;
    const percents = sharePercents(values);
    const textOf = loyalty.count ? countText : moneyText;
    list.replaceChildren(...labels.map((label, index) => {
      const item = document.createElement('li');
      const swatch = document.createElement('span');
      swatch.className = 'swatch';
      swatch.style.background = repeat && once
        ? 'linear-gradient(to bottom, ' + colors[index] + ' 50%, ' + (loyalty.tone || companion)(colors[index]) + ' 50%)'
        : colors[index];
      const text = document.createElement('div');
      const name = document.createElement('div');
      name.className = 'name';
      name.textContent = label;
      text.append(name);
      if (repeat && once) {
        text.append(
          pieceButton(list, label + ' · مشتری ثابت', 'ثابت ' + textOf(repeat[index]), (loyalty.repeatBuyers || [])[index]),
          pieceButton(list, label + ' · تک‌خرید', 'تک‌خرید ' + textOf(once[index]), (loyalty.onceBuyers || [])[index]),
        );
      } else {
        const meta = document.createElement('div');
        meta.className = 'meta';
        meta.textContent = textOf(values[index]);
        text.append(meta);
      }
      const pct = document.createElement('b');
      pct.className = 'pct';
      pct.style.color = colors[index];
      pct.textContent = fa(percents[index]) + '٪';
      item.append(swatch, text, pct);
      return item;
    }));
  }

  function shareDoughnut(labels, values, repeat, once, buyers, options) {
    if (!labels || !labels.length) return null;
    const asCount = !!(options && options.count);
    const palette = ['#0ea5e9', '#f97316', '#8b5cf6', '#10b981', '#ec4899', '#84cc16'];
    const colors = labels.map((_, index) => palette[index % palette.length]);
    const tone = soften;
    const split = Array.isArray(repeat) && Array.isArray(once);
    const people = buyers || {};
    const tracked = !!(people.repeat || people.once);
    const sliceLabels = [];
    const data = [];
    const background = [];
    const kinds = [];
    const customers = [];
    const pushSlice = (label, value, color, kind, group) => {
      if (!value) return;
      sliceLabels.push(label);
      data.push(value);
      background.push(color);
      kinds.push(kind);
      if (tracked) customers.push(group || []);
    };
    labels.forEach((label, index) => {
      if (!split) {
        pushSlice(label, Number(values[index]) || 0, colors[index], '');
        return;
      }
      pushSlice(label, Number(repeat[index]) || 0, colors[index], 'مشتری ثابت', (people.repeat || [])[index]);
      pushSlice(label, Number(once[index]) || 0, tone(colors[index]), 'تک‌خرید', (people.once || [])[index]);
    });
    const totals = split
      ? labels.map((_, index) => (Number(repeat[index]) || 0) + (Number(once[index]) || 0))
      : values;
    return {
      type: 'doughnut',
      loyalty: { labels, values: totals, repeat, once, colors, tone, count: asCount, repeatBuyers: people.repeat, onceBuyers: people.once },
      data: {
        labels: sliceLabels,
        datasets: [{
          data,
          kinds,
          customers: tracked ? customers : null,
          backgroundColor: background,
          borderColor: '#ffffff',
          borderWidth: 4,
          hoverOffset: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        plugins: {
          legend: { display: false },
          tooltip: {
            rtl: true,
            callbacks: {
              label: (ctx) => {
                const total = ctx.dataset.data.reduce((sum, n) => sum + (Number(n) || 0), 0);
                const pct = total ? Math.round((Number(ctx.parsed) || 0) / total * 100) : 0;
                const kind = ctx.dataset.kinds[ctx.dataIndex];
                const prefix = kind ? kind + ' · ' : '';
                const amount = asCount ? countText(ctx.parsed) : moneyText(ctx.parsed);
                return ' ' + prefix + amount + ' · ' + fa(pct) + '٪';
              },
            },
          },
        },
      },
    };
  }

  function loyaltyLegend() {
    return {
      position: 'top',
      rtl: true,
      labels: {
        boxWidth: 10,
        boxHeight: 10,
        padding: 10,
        color: '#334155',
        font: { family: 'Vazirmatn', size: 11, weight: '800' },
      },
    };
  }

  function loyaltySets(pairs) {
    const single = pairs.length === 1;
    return pairs.flatMap((pair) => {
      const stack = pair.stack || 'loyalty';
      const pale = Array.isArray(pair.color) ? pair.color.map((color) => soften(color)) : soften(pair.color);
      return [
        {
          label: single ? 'مشتری ثابت' : pair.label + ' · ثابت',
          data: pair.repeat,
          customers: pair.repeatBuyers || null,
          backgroundColor: pair.color,
          borderRadius: 6,
          stack,
        },
        {
          label: single ? 'تک‌خرید' : pair.label + ' · تک‌خرید',
          data: pair.once,
          customers: pair.onceBuyers || null,
          backgroundColor: pale,
          borderRadius: 6,
          stack,
        },
      ];
    });
  }

  function pairBar(labels, pairs, horizontal, kind, valueAxis) {
    if (!labels || !labels.length) return null;
    const valueScale = Object.assign({
      stacked: true,
      beginAtZero: true,
      grid,
      ticks: moneyTicks(pairs.flatMap((pair) => [].concat(pair.repeat || [], pair.once || []))),
    }, valueAxis || {});
    const categoryScale = {
      stacked: true,
      grid: { display: false },
      border: { display: false },
      ticks: categoryTicks(),
    };
    return {
      type: 'bar',
      data: { labels, datasets: loyaltySets(pairs) },
      options: {
        indexAxis: horizontal ? 'y' : 'x',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: loyaltyLegend(), tooltip: tip(kind, true) },
        scales: {
          x: horizontal ? valueScale : categoryScale,
          y: horizontal ? categoryScale : valueScale,
        },
      },
    };
  }

  function billionAxis(values) {
    const ticks = moneyTicks(values);
    return {
      grace: '8%',
      border: { display: false },
      ticks: {
        color: '#64748b',
        padding: 6,
        stepSize: ticks.stepSize,
        maxRotation: 0,
        font: { family: 'Vazirmatn', size: 11, weight: '700' },
        callback: ticks.callback,
      },
    };
  }

  function totalsOf(repeat, once) {
    return (repeat || []).map((n, index) => (Number(n) || 0) + (Number((once || [])[index]) || 0));
  }

  function productBars(labels, repeat, once, buyers) {
    const people = buyers || {};
    return pairBar(labels, [{
      repeat, once, color: '#1e40af', repeatBuyers: people.repeat, onceBuyers: people.once,
    }], true, undefined, billionAxis(totalsOf(repeat, once)));
  }

  function guildBars(labels, repeat, once, buyers) {
    const people = buyers || {};
    return pairBar(labels, [{
      repeat, once, color: '#0e7490', repeatBuyers: people.repeat, onceBuyers: people.once,
    }], false, undefined, billionAxis(totalsOf(repeat, once)));
  }

  function teamBars(experts) {
    const labels = experts.labels || [];
    if (!labels.length) return null;
    const money = [].concat(experts.sales || [], experts.profit || [], experts.commission || []);
    const maxDeals = Math.max(0, ...(experts.deals || []).map((n) => Number(n) || 0));
    const ticks = moneyTicks(money);
    const moneyTick = {
      color: '#64748b',
      maxRotation: 0,
      font: { family: 'Vazirmatn', size: 11, weight: '700' },
      stepSize: ticks.stepSize,
      callback: ticks.callback,
    };
    return {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'فروش', data: experts.sales, backgroundColor: '#0e7490', borderRadius: 6, xAxisID: 'x', maxBarThickness: 16 },
          { label: 'سود', data: experts.profit, backgroundColor: '#059669', borderRadius: 6, xAxisID: 'x', maxBarThickness: 16 },
          { label: 'کارمزد', data: experts.commission, backgroundColor: '#d97706', borderRadius: 6, xAxisID: 'x', maxBarThickness: 16 },
          {
            type: 'line',
            label: 'معامله',
            data: experts.deals,
            xAxisID: 'x2',
            borderColor: '#2563eb',
            backgroundColor: '#2563eb',
            pointRadius: 5,
            pointHoverRadius: 7,
            pointBackgroundColor: '#2563eb',
            pointBorderColor: '#fff',
            pointBorderWidth: 2,
            borderWidth: 2,
            tension: 0.25,
          },
        ],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: loyaltyLegend(),
          tooltip: {
            rtl: true,
            callbacks: {
              label: (ctx) => {
                if (ctx.dataset.label === 'معامله') return ' معامله ' + fa(valueOf(ctx));
                return ' ' + ctx.dataset.label + ' ' + moneyText(valueOf(ctx));
              },
            },
          },
        },
        scales: {
          y: {
            grid: { display: false },
            border: { display: false },
            ticks: categoryTicks(),
          },
          x: {
            position: 'bottom',
            beginAtZero: true,
            grace: '8%',
            grid,
            border: { display: false },
            ticks: moneyTick,
          },
          x2: {
            position: 'top',
            beginAtZero: true,
            grace: '12%',
            grid: { display: false },
            border: { display: false },
            ticks: {
              color: '#2563eb',
              precision: 0,
              stepSize: maxDeals <= 12 ? 1 : undefined,
              font: { family: 'Vazirmatn', size: 11, weight: '800' },
              callback: (value) => fa(value),
            },
            title: {
              display: true,
              text: 'تعداد معامله',
              color: '#2563eb',
              font: { family: 'Vazirmatn', size: 11, weight: '800' },
            },
          },
        },
      },
    };
  }

  function invoiceStack(labels, received, remaining, ids, customers) {
    if (!labels || !labels.length) return null;
    const got = received || [];
    const left = remaining || [];
    const invoiceIds = ids || [];
    const names = customers || [];
    const totals = got.map((n, index) => (Number(n) || 0) + (Number(left[index]) || 0));
    const ticks = moneyTicks(totals);
    return {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'وصول‌شده',
            data: got,
            backgroundColor: '#10b981',
            hoverBackgroundColor: '#059669',
            stack: 'invoice',
            borderRadius: (ctx) => {
              const open = Number(left[ctx.dataIndex]) || 0;
              return open > 0 ? { bottomLeft: 4, bottomRight: 4 } : 4;
            },
            maxBarThickness: 22,
            categoryPercentage: 0.92,
            barPercentage: 0.92,
            invoiceIds,
          },
          {
            label: 'باقی‌مانده',
            data: left,
            backgroundColor: '#f59e0b',
            hoverBackgroundColor: '#d97706',
            stack: 'invoice',
            borderRadius: (ctx) => {
              const paid = Number(got[ctx.dataIndex]) || 0;
              return paid > 0 ? { topLeft: 4, topRight: 4 } : 4;
            },
            maxBarThickness: 22,
            categoryPercentage: 0.92,
            barPercentage: 0.92,
            invoiceIds,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onHover: (evt, elements, chart) => {
          chart.canvas.style.cursor = salesBase && elements && elements.length ? 'pointer' : 'default';
        },
        onClick: (evt, elements) => {
          const hit = elements && elements[0];
          const id = hit && invoiceIds[hit.index];
          if (id && salesBase) window.location.assign(salesBase + id + '/');
        },
        plugins: {
          legend: {
            position: 'top',
            align: 'end',
            rtl: true,
            labels: { boxWidth: 12, boxHeight: 12, padding: 14 },
          },
          tooltip: {
            rtl: true,
            callbacks: {
              title: (items) => {
                const item = items && items[0];
                if (!item) return '';
                const name = names[item.dataIndex] || '';
                const number = labels[item.dataIndex] || item.label || '';
                if (!name) return number;
                return [name, 'فاکتور ' + number];
              },
              label: (ctx) => ' ' + ctx.dataset.label + ' ' + moneyText(valueOf(ctx)),
            },
          },
        },
        scales: {
          x: {
            stacked: true,
            grid,
            ticks: {
              ...categoryTicks(),
              autoSkip: true,
              maxRotation: 0,
              minRotation: 0,
              font: { family: 'Vazirmatn', size: labels.length > 20 ? 10 : 12, weight: '700' },
            },
          },
          y: { stacked: true, beginAtZero: true, grid, ticks },
        },
      },
    };
  }

  const checkWeek = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'];
  const checkMonths = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];

  function gregorianToJalali(gy, gm, gd) {
    const gdm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
    let jy;
    if (gy > 1600) {
      jy = 979;
      gy -= 1600;
    } else {
      jy = 0;
      gy -= 621;
    }
    const gy2 = gm > 2 ? gy + 1 : gy;
    let days = 365 * gy + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100) + Math.floor((gy2 + 399) / 400) - 80 + gd + gdm[gm - 1];
    jy += 33 * Math.floor(days / 12053);
    days %= 12053;
    jy += 4 * Math.floor(days / 1461);
    days %= 1461;
    if (days > 365) {
      jy += Math.floor((days - 1) / 365);
      days = (days - 1) % 365;
    }
    if (days < 186) return [jy, 1 + Math.floor(days / 31), 1 + (days % 31)];
    return [jy, 7 + Math.floor((days - 186) / 30), 1 + ((days - 186) % 30)];
  }

  function jalaliToGregorian(jy, jm, jd) {
    jy += 1595;
    let days = -355668 + (365 * jy) + (Math.floor(jy / 33) * 8) + Math.floor(((jy % 33) + 3) / 4) + jd;
    if (jm < 7) days += (jm - 1) * 31;
    else days += ((jm - 7) * 30) + 186;
    let gy = 400 * Math.floor(days / 146097);
    days %= 146097;
    if (days > 36524) {
      days -= 1;
      gy += 100 * Math.floor(days / 36524);
      days %= 36524;
      if (days >= 365) days += 1;
    }
    gy += 4 * Math.floor(days / 1461);
    days %= 1461;
    if (days > 365) {
      gy += Math.floor((days - 1) / 365);
      days = (days - 1) % 365;
    }
    let gd = days + 1;
    const leap = (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0;
    const lengths = [0, 31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let month = 1;
    while (month <= 12 && gd > lengths[month]) {
      gd -= lengths[month];
      month += 1;
    }
    return [gy, month, gd];
  }

  function jalaliMonthDays(year, month) {
    if (month <= 6) return 31;
    if (month <= 11) return 30;
    const back = gregorianToJalali(...jalaliToGregorian(year, 12, 30));
    return back[0] === year && back[1] === 12 && back[2] === 30 ? 30 : 29;
  }

  function jalaliWeekOffset(year, month) {
    const [gy, gm, gd] = jalaliToGregorian(year, month, 1);
    return (new Date(gy, gm - 1, gd).getDay() + 1) % 7;
  }

  function monthStamp(year, month) {
    return year * 12 + month;
  }

  function checkChevron(direction) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', '18');
    svg.setAttribute('height', '18');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2.4');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', direction === 'next' ? 'M14 6l-6 6 6 6' : 'M10 6l6 6-6 6');
    svg.appendChild(path);
    return svg;
  }

  function checkChipTone(status) {
    const compact = String(status || '').replace(/\u200c/g, '').replace(/ /g, '');
    if (compact.startsWith('وصول')) return 'is-cleared';
    if (compact.includes('برگشت') || compact === 'سررسیدگذشته') return 'is-bounced';
    if (compact === 'درانتظار') return 'is-pending';
    return '';
  }

  function renderCheckCalendar(el, due) {
    el.replaceChildren();
    const focus = (due && due.focus) || [1405, 1];
    const start = (due && due.start) || focus;
    const end = (due && due.end) || focus;
    const marks = (due && due.marks) || {};
    let year = Number(focus[0]);
    let month = Number(focus[1]);
    const nav = document.createElement('div');
    nav.className = 'check-nav';
    const prev = document.createElement('button');
    prev.type = 'button';
    prev.className = 'check-nav-btn';
    prev.setAttribute('aria-label', 'ماه قبل');
    prev.appendChild(checkChevron('prev'));
    const title = document.createElement('h3');
    title.className = 'check-month-title';
    const next = document.createElement('button');
    next.type = 'button';
    next.className = 'check-nav-btn';
    next.setAttribute('aria-label', 'ماه بعد');
    next.appendChild(checkChevron('next'));
    nav.append(prev, title, next);
    const grid = document.createElement('div');
    grid.className = 'check-grid';

    function paint() {
      const here = monthStamp(year, month);
      title.textContent = checkMonths[month - 1] + ' ' + String(year).replace(/\d/g, (ch) => '۰۱۲۳۴۵۶۷۸۹'[ch]);
      prev.disabled = here <= monthStamp(start[0], start[1]);
      next.disabled = here >= monthStamp(end[0], end[1]);
      grid.replaceChildren();
      checkWeek.forEach((name) => {
        const head = document.createElement('div');
        head.className = 'check-head';
        head.textContent = name;
        grid.appendChild(head);
      });
      const offset = jalaliWeekOffset(year, month);
      for (let i = 0; i < offset; i += 1) grid.appendChild(document.createElement('div'));
      const length = jalaliMonthDays(year, month);
      for (let day = 1; day <= length; day += 1) {
        const items = marks[year + '-' + month + '-' + day] || [];
        const cell = document.createElement('div');
        cell.className = 'check-day';
        const num = document.createElement('div');
        num.className = 'check-num';
        num.textContent = fa(day);
        cell.appendChild(num);
        items.forEach((chk) => {
          const tone = checkChipTone(chk.status);
          const chip = document.createElement(chk.invoice && salesBase ? 'a' : 'div');
          chip.className = tone ? 'check-chip ' + tone : 'check-chip';
          if (chk.invoice && salesBase) chip.href = salesBase + chk.invoice + '/';
          const name = document.createElement('span');
          name.textContent = chk.name || 'چک';
          const amount = document.createElement('span');
          amount.className = 'check-amt';
          amount.textContent = moneyText(chk.amount);
          chip.appendChild(name);
          chip.appendChild(amount);
          if (chk.status) {
            const state = document.createElement('span');
            state.className = 'check-state';
            state.textContent = chk.status;
            chip.appendChild(state);
          }
          cell.appendChild(chip);
        });
        grid.appendChild(cell);
      }
    }

    function move(step) {
      const index = year * 12 + (month - 1) + step;
      const nextYear = Math.floor(index / 12);
      const nextMonth = index - nextYear * 12 + 1;
      const stamp = monthStamp(nextYear, nextMonth);
      if (stamp < monthStamp(start[0], start[1]) || stamp > monthStamp(end[0], end[1])) return;
      year = nextYear;
      month = nextMonth;
      paint();
    }

    prev.addEventListener('click', () => move(-1));
    next.addEventListener('click', () => move(1));
    el.append(nav, grid);
    paint();
  }

  const builders = {
    dailyChart: (d) => d.monthlyProfit && areaTrend(
      d.monthlyProfit.axis || d.monthlyProfit.labels,
      d.monthlyProfit.salesRepeat || d.monthlyProfit.sales,
      d.monthlyProfit.salesOnce || [],
      d.monthlyProfit.profitRepeat || d.monthlyProfit.profit,
      d.monthlyProfit.profitOnce || [],
      {
        salesRepeat: d.monthlyProfit.salesRepeatBuyers,
        salesOnce: d.monthlyProfit.salesOnceBuyers,
        profitRepeat: d.monthlyProfit.profitRepeatBuyers,
        profitOnce: d.monthlyProfit.profitOnceBuyers,
      },
    ),
    ticketChart: (d) => d.ticket && shareDoughnut(d.ticket.labels, d.ticket.values, d.ticket.repeat, d.ticket.once, { repeat: d.ticket.repeatBuyers, once: d.ticket.onceBuyers }, { count: true }),
    saleTypeChart: (d) => d.saleType && shareDoughnut(d.saleType.labels, d.saleType.values, d.saleType.repeat, d.saleType.once, { repeat: d.saleType.repeatBuyers, once: d.saleType.onceBuyers }),
    customerTypeChart: (d) => d.customerType && guildBars(d.customerType.labels, d.customerType.repeat || d.customerType.values, d.customerType.once || [], { repeat: d.customerType.repeatBuyers, once: d.customerType.onceBuyers }),
    provinceChart: (d) => d.province && pairBar(d.province.labels, [{
      repeat: d.province.repeat, once: d.province.once, color: '#0f766e',
      repeatBuyers: d.province.repeatBuyers, onceBuyers: d.province.onceBuyers,
    }], true),
    productChart: (d) => d.product && productBars(d.product.labels, d.product.repeat, d.product.once, { repeat: d.product.repeatBuyers, once: d.product.onceBuyers }),
    monthlyTypeChart: (d) => d.monthlyType && pairBar(d.monthlyType.labels, [
      { label: 'نقدی', repeat: d.monthlyType.cashRepeat, once: d.monthlyType.cashOnce, color: '#0f766e', stack: 'cash', repeatBuyers: d.monthlyType.cashRepeatBuyers, onceBuyers: d.monthlyType.cashOnceBuyers },
      { label: 'قسطی', repeat: d.monthlyType.instRepeat, once: d.monthlyType.instOnce, color: '#6d28d9', stack: 'inst', repeatBuyers: d.monthlyType.instRepeatBuyers, onceBuyers: d.monthlyType.instOnceBuyers },
    ]),
    invoiceChart: (d) => d.invoices && invoiceStack(d.invoices.labels, d.invoices.received, d.invoices.outstanding, d.invoices.ids, d.invoices.customers),
    financeChart: (d) => d.collection && shareDoughnut(d.collection.labels, d.collection.values, d.collection.repeat, d.collection.once, { repeat: d.collection.repeatBuyers, once: d.collection.onceBuyers }),
    methodChart: (d) => d.methods && shareDoughnut(d.methods.labels, d.methods.values, d.methods.repeat, d.methods.once, { repeat: d.methods.repeatBuyers, once: d.methods.onceBuyers }),
    checkChart: () => null,
    teamChart: (d) => d.experts && teamBars(d.experts),
    trendChart: (d) => {
      if (!d.trend || !(d.trend.labels || []).length) return null;
      const names = d.trend.levelNames || [];
      const spec = bar(d.trend.labels, [{ label: 'سود ماه', data: d.trend.values, backgroundColor: d.trend.colors, borderRadius: 8 }]);
      spec.levelLegend = d.trend.legend || [];
      spec.options.plugins.legend = { display: false };
      spec.options.plugins.tooltip = {
        rtl: true,
        callbacks: {
          label: (ctx) => {
            const level = names[ctx.dataIndex] || '';
            const money = moneyText(valueOf(ctx));
            return level ? ' ' + level + ' · ' + money : ' ' + money;
          },
        },
      };
      return spec;
    },
  };

  const months = payload.months || [];
  const chartsUrl = payload.chartsUrl || '';
  const rangeLoads = {};
  const kpiByRange = { all: payload.kpis || [] };

  function kpiText(value, plain) {
    const n = Math.round(Number(value) || 0);
    if (plain) return String(n).replace(/\d/g, (digit) => '۰۱۲۳۴۵۶۷۸۹'[digit]);
    return fa(n);
  }

  function paintKpis(list) {
    const root = document.querySelector('[data-kpis]');
    if (!root || !list) return;
    list.forEach((kpi) => {
      const el = root.querySelector('[data-kpi="' + kpi.key + '"]');
      if (!el) return;
      el.textContent = kpiText(kpi.value, kpi.plain || el.hasAttribute('data-plain'));
    });
  }

  function spanKey(from, to) {
    if (!from || !to || !months.length) return 'all';
    if (from > to) {
      const swap = from;
      from = to;
      to = swap;
    }
    if (from === months[0].key && to === months[months.length - 1].key) return 'all';
    return from + '..' + to;
  }

  function loadCharts(key) {
    if (key === 'all' || byRange[key]) return Promise.resolve(byRange[key] || byRange.all || {});
    if (rangeLoads[key]) return rangeLoads[key];
    const parts = key.split('..');
    const url = new URL(chartsUrl, window.location.origin);
    url.searchParams.set('from', parts[0]);
    url.searchParams.set('to', parts[1]);
    const page = new URL(window.location.href);
    ['person', 'month', 'tmonth'].forEach((name) => {
      const value = page.searchParams.get(name);
      if (value) url.searchParams.set(name, value);
    });
    rangeLoads[key] = fetch(url, { headers: { Accept: 'application/json' } })
      .then((res) => {
        if (!res.ok) throw new Error('range');
        return res.json();
      })
      .then((data) => {
        byRange[key] = data.charts || {};
        if (data.kpis) kpiByRange[key] = data.kpis;
        return byRange[key];
      })
      .finally(() => {
        delete rangeLoads[key];
      });
    return rangeLoads[key];
  }

  function renderLevelLegend(card, levels) {
    if (!card) return;
    let list = card.querySelector('[data-level-legend]');
    if (!levels || !levels.length) {
      if (list) list.remove();
      return;
    }
    if (!list) {
      list = document.createElement('ul');
      list.className = 'chart-levels';
      list.dataset.levelLegend = '';
      card.appendChild(list);
    }
    list.replaceChildren(...levels.map((level) => {
      const item = document.createElement('li');
      const swatch = document.createElement('span');
      swatch.className = 'swatch';
      swatch.style.background = level.color;
      item.append(swatch, document.createTextNode(level.name));
      return item;
    }));
  }

  function mount(id, range) {
    const el = document.getElementById(id);
    const build = builders[id];
    if (!el || !build) return;
    const data = byRange[range] || byRange.all || {};
    if (id === 'checkChart') {
      renderCheckCalendar(el, data.checkDue);
      return;
    }
    const spec = build(data);
    const existing = Chart.getChart(el);
    if (existing) existing.destroy();
    const card = el.closest('[data-chart]');
    const shareList = card?.querySelector('[data-share]');
    if (!spec) {
      if (shareList) shareList.replaceChildren();
      renderLevelLegend(card, null);
      return;
    }
    if (spec.options && (spec.data.datasets || []).some((dataset) => dataset.customers)) watchCursor(spec);
    new Chart(el, spec);
    if (shareList && spec.loyalty) renderShare(el, spec.loyalty);
    renderLevelLegend(card, spec.levelLegend);
  }

  document.addEventListener('click', (event) => {
    if (!event.target.closest('[data-customers-back]')) return;
    hideCustomers();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') hideCustomers();
  });

  window.addEventListener('resize', () => {
    const page = customersPage();
    if (page && !page.hidden) placeCustomersPage();
  });

  document.querySelectorAll('[data-chart]').forEach((card) => {
    const id = card.dataset.chart;
    const from = card.querySelector('[data-from]');
    const to = card.querySelector('[data-to]');
    function currentKey() {
      if (!from || !to) return 'all';
      if (from.value && to.value && from.value > to.value) {
        const swap = from.value;
        from.value = to.value;
        to.value = swap;
      }
      return spanKey(from.value, to.value);
    }
    function apply() {
      const key = currentKey();
      hideCustomers(card);
      const job = loadCharts(key);
      if (byRange[key]) {
        mount(id, key);
        return;
      }
      card.classList.add('is-loading');
      job.then(() => mount(id, key)).catch(() => mount(id, 'all')).finally(() => {
        card.classList.remove('is-loading');
      });
    }
    if (from) from.addEventListener('change', apply);
    if (to) to.addEventListener('change', apply);
    mount(id, 'all');
  });

  const kpiPanel = document.querySelector('[data-kpi-panel]');
  if (kpiPanel) {
    const from = kpiPanel.querySelector('[data-from]');
    const to = kpiPanel.querySelector('[data-to]');
    const cards = document.querySelector('[data-kpis]');
    function currentKey() {
      if (!from || !to) return 'all';
      if (from.value && to.value && from.value > to.value) {
        const swap = from.value;
        from.value = to.value;
        to.value = swap;
      }
      return spanKey(from.value, to.value);
    }
    function applyKpis() {
      const key = currentKey();
      const ready = kpiByRange[key];
      if (ready) {
        paintKpis(ready);
        return;
      }
      if (cards) cards.classList.add('is-loading');
      loadCharts(key).then(() => paintKpis(kpiByRange[key])).catch(() => paintKpis(kpiByRange.all)).finally(() => {
        if (cards) cards.classList.remove('is-loading');
      });
    }
    if (from) from.addEventListener('change', applyKpis);
    if (to) to.addEventListener('change', applyKpis);
  }
})();
