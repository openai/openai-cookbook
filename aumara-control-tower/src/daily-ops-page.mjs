export function dailyOpsPage() {
  return `<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>AUMARA Daily Ops</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b0d0c;
      --panel: #131714;
      --panel-2: #191e1a;
      --line: #29302a;
      --text: #f6f4ec;
      --muted: #9ca69e;
      --green: #8bd450;
      --lime: #c7f36b;
      --amber: #ffc857;
      --red: #ff6b63;
      --blue: #73b7ff;
      --radius: 18px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 80% 0%, rgba(139,212,80,.12), transparent 34rem),
        var(--bg);
      color: var(--text);
      font: 15px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
    }
    button, input { font: inherit; }
    .shell { width: min(1480px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 52px; }
    .topbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 24px; }
    .eyebrow { color: var(--green); font-weight: 800; letter-spacing: .11em; text-transform: uppercase; font-size: 12px; }
    h1 { margin: 5px 0 4px; font-size: clamp(30px, 4vw, 54px); letter-spacing: -.045em; line-height: 1; }
    .sub { color: var(--muted); }
    .quality { border: 1px solid var(--line); border-radius: 999px; padding: 8px 12px; font-weight: 750; white-space: nowrap; }
    .quality.ready { color: var(--lime); }
    .quality.partial { color: var(--amber); }
    .quality.blocked { color: var(--red); }
    .source-strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 20px; }
    .source { background: rgba(19,23,20,.86); border: 1px solid var(--line); border-radius: 14px; padding: 13px 14px; }
    .source-head { display: flex; justify-content: space-between; gap: 10px; align-items: center; font-weight: 800; text-transform: uppercase; }
    .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 7px; background: var(--muted); }
    .healthy .dot { background: var(--green); box-shadow: 0 0 0 4px rgba(139,212,80,.12); }
    .stale .dot { background: var(--amber); }
    .blocked .dot { background: var(--red); }
    .source-meta { margin-top: 7px; color: var(--muted); font-size: 12px; min-height: 34px; }
    .group { margin-top: 24px; }
    .group h2 { margin: 0 0 12px; font-size: 18px; letter-spacing: -.01em; }
    .cards { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; }
    .card { border: 1px solid var(--line); background: var(--panel); border-radius: var(--radius); padding: 16px; min-height: 110px; }
    .label { color: var(--muted); font-size: 12px; font-weight: 750; text-transform: uppercase; letter-spacing: .04em; }
    .value { font-size: clamp(26px, 3vw, 40px); font-weight: 850; letter-spacing: -.04em; margin-top: 12px; line-height: 1; }
    .value.unavailable { color: #5d675f; }
    .split { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(320px, .75fr); gap: 12px; }
    .panel { border: 1px solid var(--line); background: var(--panel); border-radius: var(--radius); padding: 18px; }
    .panel h3 { margin: 0 0 14px; font-size: 15px; }
    .bar-row { display: grid; grid-template-columns: 150px minmax(0, 1fr) 80px; align-items: center; gap: 10px; margin: 11px 0; }
    .bar-label { color: var(--muted); font-size: 13px; }
    .bar-track { background: #222823; height: 10px; border-radius: 999px; overflow: hidden; }
    .bar { height: 100%; min-width: 2px; border-radius: inherit; background: linear-gradient(90deg, var(--green), var(--lime)); }
    .bar.negative { background: linear-gradient(90deg, #e98552, var(--red)); }
    .bar.blue { background: linear-gradient(90deg, #438cd9, var(--blue)); }
    .bar-amount { text-align: right; font-variant-numeric: tabular-nums; }
    .issues { margin: 0; padding-left: 18px; color: var(--muted); }
    .issues li + li { margin-top: 7px; }
    .table-wrap { overflow: auto; border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel); }
    table { width: 100%; border-collapse: collapse; min-width: 980px; }
    th, td { text-align: left; padding: 12px 14px; border-bottom: 1px solid var(--line); vertical-align: top; }
    th { color: var(--muted); font-size: 11px; letter-spacing: .06em; text-transform: uppercase; background: #111411; position: sticky; top: 0; }
    td { font-size: 13px; }
    tr:last-child td { border-bottom: 0; }
    .badge { display: inline-block; border: 1px solid var(--line); border-radius: 999px; padding: 3px 8px; font-size: 11px; }
    .attention { color: var(--amber); border-color: rgba(255,200,87,.4); }
    a { color: var(--blue); }
    .empty { padding: 32px; text-align: center; color: var(--muted); }
    .auth {
      position: fixed; inset: 0; z-index: 10; display: grid; place-items: center;
      padding: 20px; background: rgba(6,8,7,.88); backdrop-filter: blur(12px);
    }
    .auth[hidden] { display: none; }
    .auth-card { width: min(440px, 100%); background: var(--panel-2); border: 1px solid var(--line); border-radius: 22px; padding: 24px; }
    .auth-card h2 { margin: 0 0 8px; }
    .auth-card p { color: var(--muted); }
    .auth-row { display: flex; gap: 8px; margin-top: 16px; }
    .auth input { width: 100%; min-width: 0; border: 1px solid var(--line); color: var(--text); background: #0c0f0d; border-radius: 11px; padding: 11px 12px; }
    .auth button { border: 0; border-radius: 11px; background: var(--green); color: #0b1307; font-weight: 850; padding: 11px 16px; cursor: pointer; }
    .auth-error { min-height: 20px; color: var(--red); font-size: 12px; margin-top: 10px; }
    @media (max-width: 1000px) {
      .source-strip { grid-template-columns: repeat(2, 1fr); }
      .cards { grid-template-columns: repeat(3, 1fr); }
      .split { grid-template-columns: 1fr; }
    }
    @media (max-width: 620px) {
      .shell { width: min(100% - 20px, 1480px); padding-top: 18px; }
      .topbar { display: block; }
      .quality { display: inline-block; margin-top: 12px; }
      .source-strip { grid-template-columns: 1fr 1fr; }
      .cards { grid-template-columns: repeat(2, 1fr); }
      .card { min-height: 96px; }
      .bar-row { grid-template-columns: 110px minmax(0, 1fr) 66px; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <div class="topbar">
      <div>
        <div class="eyebrow">AUMARA / EL CID · Control Tower</div>
        <h1>Daily Ops</h1>
        <div class="sub" id="subtitle">Загрузка проверенного снимка…</div>
      </div>
      <div class="quality blocked" id="quality">NO DATA</div>
    </div>

    <section class="source-strip" id="sources"></section>

    <section class="group">
      <h2>Гостевые операции</h2>
      <div class="cards" id="guestCards"></div>
    </section>
    <section class="group">
      <h2>Бронирования и стоимость</h2>
      <div class="cards" id="hotelCards"></div>
    </section>
    <section class="group">
      <h2>Ресторан и исполнение</h2>
      <div class="cards" id="opsCards"></div>
    </section>

    <section class="group split">
      <div class="panel">
        <h3>Движение стоимости и оплат</h3>
        <div id="bars"></div>
      </div>
      <div class="panel">
        <h3>Качество данных</h3>
        <ul class="issues" id="issues"></ul>
      </div>
    </section>

    <section class="group">
      <h2>События дня</h2>
      <div class="table-wrap" id="events"></div>
    </section>
  </main>

  <div class="auth" id="auth">
    <form class="auth-card" id="authForm">
      <div class="eyebrow">Private operations</div>
      <h2>AUMARA Daily Ops</h2>
      <p>Введите отдельный токен просмотра. Он хранится только в текущей вкладке и не отправляется сторонним сервисам.</p>
      <div class="auth-row">
        <input id="token" type="password" autocomplete="current-password" aria-label="Dashboard token" required>
        <button type="submit">Открыть</button>
      </div>
      <div class="auth-error" id="authError"></div>
    </form>
  </div>

  <script>
    const sourceNames = { gmail: 'Gmail', beds24: 'Beds24', epos: 'EPOS', b24: 'B24' };
    const metricGroups = {
      guestCards: [
        ['guestEvents', 'Получено событий'],
        ['confirmedSentReplies', 'SENT ответов'],
        ['cancellationFollowUps', 'Отмен follow-up'],
        ['opsLogged', 'Ops logged'],
        ['needsDecision', 'Needs decision'],
        ['beds24NotesPending', 'Beds24 pending'],
        ['lostReplies', 'Потерянных ответов'],
        ['deliveryErrors', 'Ошибок доставки'],
        ['draftReplies', 'DRAFT — не SENT']
      ],
      hotelCards: [
        ['newBookings', 'Новых броней'],
        ['modifiedBookings', 'Изменений'],
        ['cancelledBookings', 'Отмен'],
        ['bookedRevenueAddedEur', 'Добавлено', 'eur'],
        ['bookedRevenueCancelledEur', 'Отменено', 'eur'],
        ['bookedRevenueNetEur', 'Чистое движение', 'eur'],
        ['arrivals', 'Заездов'],
        ['departures', 'Выездов'],
        ['occupiedRoomNights', 'Room nights']
      ],
      opsCards: [
        ['restaurantSalesGrossEur', 'Продажи EPOS', 'eur'],
        ['restaurantVatEur', 'VAT EPOS', 'eur'],
        ['restaurantCashEur', 'Cash', 'eur'],
        ['restaurantCardEur', 'Card', 'eur'],
        ['restaurantRefundsEur', 'Возвраты', 'eur'],
        ['restaurantTransactions', 'Транзакций'],
        ['b24OpenTasks', 'B24 открыто'],
        ['b24ClosedToday', 'B24 закрыто'],
        ['b24OverdueTasks', 'B24 просрочено']
      ]
    };
    const money = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 2 });
    const count = new Intl.NumberFormat('ru-RU');
    const dateTime = new Intl.DateTimeFormat('ru-RU', {
      timeZone: 'Europe/Madrid', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
    });

    function text(value) { return value === null || value === undefined || value === '' ? '—' : String(value); }
    function format(value, kind) {
      if (value === null || value === undefined) return '—';
      return kind === 'eur' ? money.format(Number(value)) : count.format(Number(value));
    }
    function el(tag, className, value) {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (value !== undefined) node.textContent = value;
      return node;
    }
    function renderCards(target, rows, metrics) {
      const root = document.getElementById(target);
      root.replaceChildren();
      for (const [key, label, kind] of rows) {
        const card = el('article', 'card');
        card.append(el('div', 'label', label));
        const value = el('div', 'value', format(metrics[key], kind));
        if (metrics[key] === null || metrics[key] === undefined) value.classList.add('unavailable');
        card.append(value);
        root.append(card);
      }
    }
    function renderSources(sources) {
      const root = document.getElementById('sources');
      root.replaceChildren();
      for (const source of sources) {
        const card = el('article', 'source ' + source.status);
        const head = el('div', 'source-head');
        const name = el('div');
        name.append(el('span', 'dot'), document.createTextNode(sourceNames[source.id] || source.id));
        head.append(name, el('span', 'badge', source.status));
        card.append(head);
        let detail = source.message || 'Источник в пределах SLA';
        if (source.freshnessMinutes !== null) detail += ' · ' + source.freshnessMinutes + ' мин.';
        card.append(el('div', 'source-meta', detail));
        root.append(card);
      }
    }
    function renderBars(metrics) {
      const root = document.getElementById('bars');
      root.replaceChildren();
      const rows = [
        ['Добавлено бронями', metrics.bookedRevenueAddedEur, ''],
        ['Отменено бронями', metrics.bookedRevenueCancelledEur, 'negative'],
        ['EPOS cash', metrics.restaurantCashEur, ''],
        ['EPOS card', metrics.restaurantCardEur, 'blue']
      ];
      const max = Math.max(1, ...rows.map(row => Number(row[1] || 0)));
      for (const [label, value, style] of rows) {
        const line = el('div', 'bar-row');
        line.append(el('div', 'bar-label', label));
        const track = el('div', 'bar-track');
        const bar = el('div', 'bar ' + style);
        bar.style.width = value === null || value === undefined ? '0' : Math.max(2, Number(value) / max * 100) + '%';
        track.append(bar);
        line.append(track, el('div', 'bar-amount', value === null || value === undefined ? '—' : money.format(Number(value))));
        root.append(line);
      }
    }
    function safeUrl(value) {
      try {
        const url = new URL(value);
        return url.protocol === 'https:' ? url.toString() : null;
      } catch { return null; }
    }
    function renderEvents(events) {
      const root = document.getElementById('events');
      root.replaceChildren();
      if (!events.length) {
        root.append(el('div', 'empty', 'За выбранный день событий в доступных источниках нет.'));
        return;
      }
      const table = document.createElement('table');
      const head = document.createElement('thead');
      const header = document.createElement('tr');
      for (const value of ['Время', 'Источник', 'Объект', 'Гость / Ref', 'Событие', 'Результат', 'Содержание']) {
        header.append(el('th', '', value));
      }
      head.append(header);
      const body = document.createElement('tbody');
      for (const event of events) {
        const row = document.createElement('tr');
        let at = '—';
        if (event.at && !Number.isNaN(Date.parse(event.at))) at = dateTime.format(new Date(event.at));
        row.append(el('td', '', at));
        row.append(el('td', '', sourceNames[event.source] || event.source));
        row.append(el('td', '', text(event.property)));
        row.append(el('td', '', [event.guest, event.bookingRef].filter(Boolean).join(' · ') || '—'));
        row.append(el('td', '', text(event.type).replaceAll('_', ' ')));
        const status = el('span', 'badge' + (event.requiresDecision ? ' attention' : ''), text(event.status));
        const statusCell = document.createElement('td');
        statusCell.append(status);
        row.append(statusCell);
        const summaryCell = document.createElement('td');
        const href = safeUrl(event.actionUrl);
        if (href) {
          const link = document.createElement('a');
          link.href = href; link.target = '_blank'; link.rel = 'noreferrer';
          link.textContent = text(event.summary);
          summaryCell.append(link);
        } else {
          summaryCell.textContent = text(event.summary);
        }
        row.append(summaryCell);
        body.append(row);
      }
      table.append(head, body);
      root.append(table);
    }
    function render(snapshot) {
      document.getElementById('subtitle').textContent =
        snapshot.businessDate + ' · Europe/Madrid · обновлено ' + dateTime.format(new Date(snapshot.generatedAtUtc));
      const quality = document.getElementById('quality');
      quality.className = 'quality ' + snapshot.dataQuality.status;
      quality.textContent = snapshot.dataQuality.status.toUpperCase();
      renderSources(snapshot.sources);
      for (const [target, rows] of Object.entries(metricGroups)) renderCards(target, rows, snapshot.metrics);
      renderBars(snapshot.metrics);
      const issues = document.getElementById('issues');
      issues.replaceChildren();
      const rows = snapshot.dataQuality.issues.length ? snapshot.dataQuality.issues : ['Все четыре источника в пределах SLA.'];
      for (const issue of rows) issues.append(el('li', '', issue));
      renderEvents(snapshot.events);
    }
    function markRefreshFailure() {
      const quality = document.getElementById('quality');
      quality.className = 'quality blocked';
      quality.textContent = 'REFRESH FAILED';
      document.getElementById('subtitle').textContent =
        'Свежий snapshot недоступен. Не используйте экран для решений до восстановления.';
    }
    async function load(token) {
      const response = await fetch('/api/daily-ops/latest', {
        headers: { authorization: 'Bearer ' + token },
        cache: 'no-store'
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || body.code || 'Dashboard unavailable');
      render(body);
    }
    const auth = document.getElementById('auth');
    const form = document.getElementById('authForm');
    const input = document.getElementById('token');
    const error = document.getElementById('authError');
    const saved = sessionStorage.getItem('aumara.dailyOpsToken') || '';
    input.value = saved;
    async function authenticate(token) {
      error.textContent = '';
      try {
        await load(token);
        sessionStorage.setItem('aumara.dailyOpsToken', token);
        auth.hidden = true;
        window.setInterval(
          () => load(token).catch(() => markRefreshFailure()),
          60000
        );
      } catch (problem) {
        sessionStorage.removeItem('aumara.dailyOpsToken');
        auth.hidden = false;
        error.textContent = problem.message;
      }
    }
    form.addEventListener('submit', event => {
      event.preventDefault();
      authenticate(input.value.trim());
    });
    if (saved) authenticate(saved);
  </script>
</body>
</html>`;
}
