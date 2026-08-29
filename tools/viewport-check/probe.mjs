// Cac phep do chay TRONG trang.
export const PROBE = () => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const vis = el => {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const id = el => {
    const c = el.className && typeof el.className === 'string'
      ? '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.') : '';
    return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + c;
  };
  // Co to tien nao cuon ngang duoc khong? Neu co, tran ra ngoai viewport la HOP LE
  // (bang rong hon man hinh nam trong .table-wrap { overflow-x: auto } chang han).
  const inScrollX = el => {
    for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX;
      if (ox === 'auto' || ox === 'scroll') return id(p);
    }
    return null;
  };

  // ── TRAN NGANG ──
  // raw   : dung nguyen dinh nghia "right > vw+1 hoac left < -1"
  // that  : da loai (a) phan tu nam TRON ngoai man hinh — skip-link o -9999,
  //         drawer dong bi day sang phai; (b) phan tu trong vung cuon ngang hop le.
  const overflowRaw = [];
  const overflow = [];
  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el)) continue;
    const r = el.getBoundingClientRect();
    if (!(r.right > vw + 1 || r.left < -1)) continue;
    const rec = { el: id(el), text: (el.textContent || '').trim().slice(0, 30),
                  left: Math.round(r.left), right: Math.round(r.right), vw };
    overflowRaw.push(rec);
    const fullyOff = r.right <= 0 || r.left >= vw;
    const sc = inScrollX(el);
    if (fullyOff || sc) continue;
    overflow.push({ ...rec, scrollParent: sc });
  }

  // ── TRAN CHU: chu rong hon chinh cai hop chua no ──
  // Day la phep bat "Pre-BreakouGC dai han": nut bi co duoi be rong noi dung,
  // white-space: nowrap chan xuong dong, chu tran ra ngoai hop va de len nut ben.
  const textOverflow = [];
  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el)) continue;
    const s = getComputedStyle(el);
    if (s.whiteSpace !== 'nowrap' && s.whiteSpace !== 'pre') continue;
    // Bo qua phan tu CO CHU DICH cat chu: `text-overflow: ellipsis` di kem
    // `overflow: hidden` la thiet ke, khong phai loi. Vd <summary> cua mien tru
    // trach nhiem (692c38c) co y giu mot dong va cat bang dau ba cham.
    if (s.textOverflow === 'ellipsis' && s.overflowX !== 'visible') continue;
    const t = [...el.childNodes].filter(n => n.nodeType === 3 && n.textContent.trim());
    if (!t.length) continue;
    // Bo qua hop INLINE: clientWidth cua chung luon = 0 theo spec, nen phep so
    // "chu rong hon hop" vo nghia — 208 cai <span> bao nham o lan chay dau.
    if (el.clientWidth === 0) continue;
    const rg = document.createRange();
    rg.selectNodeContents(el);
    const tw = rg.getBoundingClientRect().width;
    rg.detach?.();
    const cw = el.clientWidth
      - parseFloat(s.paddingLeft || 0) - parseFloat(s.paddingRight || 0);
    if (tw > cw + 1) {
      textOverflow.push({ el: id(el), text: (el.textContent || '').trim().slice(0, 30),
                          textW: Math.round(tw), boxW: Math.round(cw),
                          tran: Math.round(tw - cw) });
    }
  }

  // ── CHONG LAN ──
  // Bo qua phan tu da bi to tien CAT (nam ngoai vung cuon cua no). Vi du:
  // mot o trong bang da cuon khuat khoi .table-wrap van co rect hop le va tam
  // cua no roi vao cho footer dang ve — elementFromPoint tra ve footer va bao
  // "bi che" oan. Lan chay dau cho 19 cap gia kieu nay o desktop 1366px.
  // Lay TAM CUA PHAN NHIN THAY, khong phai tam cua rect day du.
  //
  // Vi sao: mot phan tu vat qua bien vung cuon thi nua duoi bi cat, ma tam cua
  // rect day du roi dung vao pixel bien — pixel do thuoc ve phan tu VE SAU
  // (footer), nen elementFromPoint tra ve footer va bao "bi che" oan.
  // Do that o iPad doc: .fib-label top=1329 bottom=1338, .table-wrap bottom=1334,
  // footer top=1334. Tam = 1334 = dung bien. Dieu kien `y > bottom + 1` khong
  // bat duoc vi 1334 khong lon hon 1335.
  // Nguy hiem hon ca cai sai: bien do PHU THUOC SO HANG du lieu, nen hom khac
  // du lieu khac thi so cap gia doi tu 2 thanh 0 hay 3 — va se hien o cot MOI
  // PHAT SINH ma khong ai biet vi sao.
  // Giao rect voi moi to tien cat; rong bang 0 nghia la khuat han -> bo qua.
  const visibleBox = (el) => {
    let r = el.getBoundingClientRect();
    let box = { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
    for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (cs.overflow === 'visible' && cs.overflowX === 'visible' && cs.overflowY === 'visible') continue;
      const b = p.getBoundingClientRect();
      box.left = Math.max(box.left, b.left);   box.right = Math.min(box.right, b.right);
      box.top = Math.max(box.top, b.top);      box.bottom = Math.min(box.bottom, b.bottom);
      if (box.right - box.left < 1 || box.bottom - box.top < 1) return null;
    }
    return box;
  };
  const overlap = [];
  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el)) continue;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const vb = visibleBox(el);
    if (!vb) continue;                       // khuat han sau vung cuon
    const x = (vb.left + vb.right) / 2, y = (vb.top + vb.bottom) / 2;
    if (x < 0 || y < 0 || x > vw || y > vh) continue;
    const hit = document.elementFromPoint(x, y);
    if (!hit || hit === el || el.contains(hit) || hit.contains(el)) continue;
    const cs = getComputedStyle(el), ch = getComputedStyle(hit);
    overlap.push({
      covered: id(el), coveredText: (el.textContent || '').trim().slice(0, 30),
      cover: id(hit), coverText: (hit.textContent || '').trim().slice(0, 30),
      coveredZ: cs.zIndex, coveredPos: cs.position,
      coverZ: ch.zIndex, coverPos: ch.position,
    });
  }

  // ── TRUC DOC ──
  const axis = [...document.body.children].filter(vis).map(el => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return { el: id(el), height: Math.round(r.height), scrollHeight: el.scrollHeight,
             minHeight: s.minHeight, flexShrink: s.flexShrink, position: s.position,
             zIndex: s.zIndex, overflowsY: el.scrollHeight > Math.round(r.height) + 1 };
  });

  // ── SO DO (khong phai co true/false) ──
  // scrollWidth cua dai tab phan anh loi ep co RAT RO: 412px khi nut bi bop
  // xuong 43px, 560px khi nut giu be rong that. Nhung phep kiem nhi phan
  // "scrollW > clientW?" DUNG o ca hai trang thai, nen no vut bo chinh tin hieu
  // do. Ghi ra day duoi dang SO de diff so duoc, dung de no chi song trong mot
  // cai co.
  const tabs = document.querySelector('.strategy-tabs');
  const metrics = tabs ? {
    tabsScrollWidth: tabs.scrollWidth,
    tabsClientWidth: tabs.clientWidth,
    tabCount: tabs.querySelectorAll('.strat-tab').length,
    tabWidths: [...tabs.querySelectorAll('.strat-tab')].map(t => Math.round(t.getBoundingClientRect().width)),
  } : null;

  // ── COT BANG: so o tieu de hien PHAI BANG so o than bang hien ──
  // Khoi @media an cot bang `.signal-table .prio-N { display: none }`. Quy tac
  // do ap cho ca <th> lan <td>, nhung neu <td> THIEU class prio thi chi hang
  // tieu de mat o — hang du lieu giu nguyen 15 o. Bang lech cot ma khong co gi
  // bao loi.
  const table = document.querySelector('.signal-table');
  let cols = null;
  if (table) {
    const vth = [...table.querySelectorAll('thead th')].filter(vis).length;
    const row = table.querySelector('tbody tr[data-ticker]');
    const vtd = row ? [...row.querySelectorAll('td')].filter(vis).length : null;
    cols = { thHien: vth, tdHien: vtd, khop: vtd === null || vth === vtd };
  }

  // ── .list-head bi KEP hay bi CAT ──
  const lh = document.querySelector('.list-head');
  let listHead = null;
  if (lh && vis(lh)) {
    const r = lh.getBoundingClientRect();
    const at = (x, y) => { const e = document.elementFromPoint(x, y); return e ? id(e) : null; };
    const cx = r.left + r.width / 2;
    listHead = { rect: { top: Math.round(r.top), bottom: Math.round(r.bottom), height: Math.round(r.height) },
                 atTopEdge: at(cx, r.top + 2), atBottomEdge: at(cx, r.bottom - 2),
                 atCenter: at(cx, r.top + r.height / 2) };
  }

  // Cau hinh THUC TE trang nhin thay — de doc baseline khong phai doan.
  const env = {
    coarse: matchMedia('(pointer: coarse)').matches,
    fine:   matchMedia('(pointer: fine)').matches,
    hover:  matchMedia('(hover: hover)').matches,
    dpr: window.devicePixelRatio,
    maxTouchPoints: navigator.maxTouchPoints,
  };

  return { vw, vh, env, metrics, cols, scrollY: Math.round(window.scrollY),
           overflowRawCount: overflowRaw.length, overflow, textOverflow, overlap, axis, listHead };
};
