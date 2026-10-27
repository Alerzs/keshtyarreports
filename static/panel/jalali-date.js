(function () {
  const FA = '۰۱۲۳۴۵۶۷۸۹';
  const MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];
  const WEEKDAYS = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'];

  function toEn(value) {
    return String(value || '').replace(/[۰-۹]/g, (ch) => String(FA.indexOf(ch))).replace(/[٠-٩]/g, (ch) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(ch)));
  }

  function toFa(value) {
    return String(value).replace(/\d/g, (ch) => FA[ch]);
  }

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
    let jm;
    let jd;
    if (days < 186) {
      jm = 1 + Math.floor(days / 31);
      jd = 1 + (days % 31);
    } else {
      jm = 7 + Math.floor((days - 186) / 30);
      jd = 1 + ((days - 186) % 30);
    }
    return [jy, jm, jd];
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
    const months = [0, 31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let gmonth = 1;
    while (gmonth <= 12 && gd > months[gmonth]) {
      gd -= months[gmonth];
      gmonth += 1;
    }
    return [gy, gmonth, gd];
  }

  function monthLength(jy, jm) {
    if (jm <= 6) return 31;
    if (jm <= 11) return 30;
    const back = gregorianToJalali(...jalaliToGregorian(jy, 12, 30));
    return back[0] === jy && back[1] === 12 && back[2] === 30 ? 30 : 29;
  }

  function pad(n) {
    return String(n).padStart(2, '0');
  }

  function formatDate(jy, jm, jd) {
    return toFa(jy + '/' + pad(jm) + '/' + pad(jd));
  }

  function parseDate(value) {
    const raw = toEn(value).trim().replace(/[-.]/g, '/');
    const match = raw.match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/);
    if (!match) return null;
    const jy = Number(match[1]);
    const jm = Number(match[2]);
    const jd = Number(match[3]);
    if (jm < 1 || jm > 12 || jd < 1 || jd > monthLength(jy, jm)) return null;
    return [jy, jm, jd];
  }

  function todayParts() {
    const now = new Date();
    return gregorianToJalali(now.getFullYear(), now.getMonth() + 1, now.getDate());
  }

  function weekdayOffset(jy, jm) {
    const g = jalaliToGregorian(jy, jm, 1);
    const weekday = new Date(g[0], g[1] - 1, g[2]).getDay();
    return (weekday + 1) % 7;
  }

  const style = document.createElement('style');
  style.textContent = [
    'input[data-jdate]{background-image:url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'18\' height=\'18\' fill=\'none\' stroke=\'%230e7490\' stroke-width=\'2\' stroke-linecap=\'round\' stroke-linejoin=\'round\'%3E%3Crect x=\'2.5\' y=\'3.5\' width=\'13\' height=\'12\' rx=\'2\'/%3E%3Cpath d=\'M2.5 7.5h13M6 2.5v3M12 2.5v3\'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:left .7rem center;padding-left:2.1rem}',
    '.jcal{position:fixed;z-index:90;width:min(320px,calc(100vw - 16px));border:1px solid #e2e8f0;border-radius:18px;background:#fff;box-shadow:0 20px 40px -12px rgba(15,23,42,.28);padding:12px;font-family:Vazirmatn,sans-serif;color:#0f172a}',
    '.jcal-bar{display:flex;align-items:center;gap:6px;margin-bottom:8px}',
    '.jcal-title{flex:1;display:flex;justify-content:center;gap:8px;min-height:36px}',
    '.jcal-title button,.jcal-nav,.jcal-foot button,.jcal-cell{border:0;background:transparent;font:inherit;cursor:pointer}',
    '.jcal-title button{font-weight:800;color:#0e7490;border-radius:10px;padding:4px 8px}',
    '.jcal-title button:hover,.jcal-nav:hover,.jcal-foot button:hover{background:#f0f9ff}',
    '.jcal-nav{width:36px;height:36px;border-radius:10px;font-size:20px;line-height:1;color:#0f172a}',
    '.jcal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}',
    '.jcal-grid.is-wide{grid-template-columns:repeat(3,1fr);gap:6px}',
    '.jcal-wd{text-align:center;font-size:11px;font-weight:800;color:#64748b;padding:4px 0}',
    '.jcal-cell{height:36px;border-radius:10px;font-size:13px;font-weight:800}',
    '.jcal-cell:hover{background:#f8fafc}',
    '.jcal-cell.is-today{box-shadow:inset 0 0 0 1.5px #0e7490;color:#0e7490}',
    '.jcal-cell.is-on,.jcal-cell.is-on:hover{background:#0e7490;color:#fff;box-shadow:none}',
    '.jcal-foot{display:flex;justify-content:space-between;gap:8px;margin-top:8px;padding-top:8px;border-top:1px solid #e2e8f0}',
    '.jcal-foot button{font-size:12px;font-weight:800;color:#0e7490;border-radius:8px;padding:6px 8px}',
  ].join('');
  document.head.appendChild(style);

  const pop = document.createElement('div');
  pop.className = 'jcal';
  pop.hidden = true;
  pop.setAttribute('role', 'dialog');
  pop.setAttribute('aria-label', 'تقویم شمسی');
  pop.innerHTML = '<div class="jcal-bar"><button type="button" class="jcal-nav" data-act="prev" aria-label="قبل">›</button><div class="jcal-title"><button type="button" data-act="months"></button><button type="button" data-act="years"></button></div><button type="button" class="jcal-nav" data-act="next" aria-label="بعد">‹</button></div><div class="jcal-grid"></div><div class="jcal-foot"><button type="button" data-act="today">امروز</button><button type="button" data-act="clear">پاک کردن</button></div>';
  document.body.appendChild(pop);

  const titleMonth = pop.querySelector('[data-act="months"]');
  const titleYear = pop.querySelector('[data-act="years"]');
  const grid = pop.querySelector('.jcal-grid');

  let input = null;
  let viewYear = 1405;
  let viewMonth = 1;
  let yearPage = 1400;
  let mode = 'days';

  function selected() {
    return input ? parseDate(input.value) : null;
  }

  function setValue(parts) {
    if (!input) return;
    input.value = parts ? formatDate(parts[0], parts[1], parts[2]) : '';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function cell(label, onClick, extra) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'jcal-cell' + (extra ? ' ' + extra : '');
    button.textContent = label;
    button.addEventListener('click', onClick);
    return button;
  }

  function renderDays() {
    grid.classList.remove('is-wide');
    grid.replaceChildren();
    WEEKDAYS.forEach((name) => {
      const mark = document.createElement('div');
      mark.className = 'jcal-wd';
      mark.textContent = name;
      grid.appendChild(mark);
    });
    const offset = weekdayOffset(viewYear, viewMonth);
    for (let i = 0; i < offset; i += 1) grid.appendChild(document.createElement('span'));
    const length = monthLength(viewYear, viewMonth);
    const picked = selected();
    const today = todayParts();
    for (let day = 1; day <= length; day += 1) {
      const on = picked && picked[0] === viewYear && picked[1] === viewMonth && picked[2] === day;
      const isToday = today[0] === viewYear && today[1] === viewMonth && today[2] === day;
      const classes = (on ? 'is-on' : '') + (isToday && !on ? ' is-today' : '');
      grid.appendChild(cell(toFa(day), () => {
        setValue([viewYear, viewMonth, day]);
        close();
      }, classes));
    }
  }

  function renderMonths() {
    grid.classList.add('is-wide');
    grid.replaceChildren();
    MONTHS.forEach((name, index) => {
      const month = index + 1;
      grid.appendChild(cell(name, () => {
        viewMonth = month;
        mode = 'days';
        render();
      }, month === viewMonth ? 'is-on' : ''));
    });
  }

  function renderYears() {
    grid.classList.add('is-wide');
    grid.replaceChildren();
    for (let year = yearPage; year < yearPage + 12; year += 1) {
      const pickedYear = year;
      grid.appendChild(cell(toFa(year), () => {
        viewYear = pickedYear;
        mode = 'days';
        render();
      }, year === viewYear ? 'is-on' : ''));
    }
  }

  function render() {
    titleMonth.textContent = MONTHS[viewMonth - 1];
    titleYear.textContent = toFa(viewYear);
    if (mode === 'months') renderMonths();
    else if (mode === 'years') renderYears();
    else renderDays();
  }

  function place() {
    if (!input) return;
    const rect = input.getBoundingClientRect();
    pop.hidden = false;
    const width = pop.offsetWidth;
    const height = pop.offsetHeight;
    let top = rect.bottom + 6;
    let left = rect.right - width;
    if (top + height > window.innerHeight - 8) top = Math.max(8, rect.top - height - 6);
    if (left < 8) left = 8;
    if (left + width > window.innerWidth - 8) left = window.innerWidth - width - 8;
    pop.style.top = top + 'px';
    pop.style.left = left + 'px';
  }

  function open(target) {
    input = target;
    const parsed = parseDate(target.value) || todayParts();
    viewYear = parsed[0];
    viewMonth = parsed[1];
    yearPage = viewYear - (((viewYear - 1320) % 12 + 12) % 12);
    mode = 'days';
    render();
    place();
  }

  function close() {
    pop.hidden = true;
    input = null;
  }

  function shift(step) {
    if (mode === 'years') {
      yearPage += step * 12;
      render();
      return;
    }
    if (mode === 'months') {
      viewYear += step;
      render();
      return;
    }
    viewMonth += step;
    if (viewMonth > 12) {
      viewMonth = 1;
      viewYear += 1;
    } else if (viewMonth < 1) {
      viewMonth = 12;
      viewYear -= 1;
    }
    render();
  }

  pop.addEventListener('click', (event) => {
    const act = event.target.closest('[data-act]');
    if (!act) return;
    if (act.dataset.act === 'prev') shift(-1);
    else if (act.dataset.act === 'next') shift(1);
    else if (act.dataset.act === 'months') {
      mode = mode === 'months' ? 'days' : 'months';
      render();
    } else if (act.dataset.act === 'years') {
      mode = mode === 'years' ? 'days' : 'years';
      yearPage = viewYear - (((viewYear - 1320) % 12 + 12) % 12);
      render();
    } else if (act.dataset.act === 'today') {
      const now = todayParts();
      setValue(now);
      close();
    } else if (act.dataset.act === 'clear') {
      setValue(null);
      close();
    }
  });

  document.addEventListener('pointerdown', (event) => {
    const field = event.target.closest('input[data-jdate]');
    if (field) {
      event.preventDefault();
      open(field);
      return;
    }
    if (!pop.hidden && !pop.contains(event.target)) close();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !pop.hidden) close();
  });

  window.addEventListener('resize', () => {
    if (!pop.hidden) place();
  });
  window.addEventListener('scroll', () => {
    if (!pop.hidden) place();
  }, true);

  window.keshtJalali = { gregorianToJalali, jalaliToGregorian, monthLength, parseDate, formatDate };
})();
