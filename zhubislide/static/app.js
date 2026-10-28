/* ZhubiSlide — front-end: form, live progress with real countdown, slide preview, my works. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
};

/* ───────────────────────── texts ───────────────────────── */
const I18N = {
  kk: {
    nav_create: "Жасау", nav_designs: "Дизайндар", nav_works: "Менің жұмыстарым", nav_how: "Қалай жұмыс істейді", nav_faq: "Сұрақтар",
    badge: "ИИ презентация генераторы · қазақша және орысша",
    h1: "Тақырыпты жаз — <em>дайын презентацияны</em> ал",
    sub: "ZhubiSlide тақырыпқа сай дизайн таңдайды, толық әрі түсінікті мәтін жазады, суреттер қояды және PowerPoint файлын береді.",
    f1: "<b>5–25</b> слайд", f2: "<b>Тақырыпқа сай</b> дизайн", f3: "<b>Нақты</b> уақыт есебі", f4: "<b>.PPTX</b> файл",
    topic: "Тақырып", topic_ph: "Мысалы: Қазақ хандығының құрылуы",
    pages: "Слайд саны", pages_hint: "қасында — дайын болу уақыты",
    slang: "Презентация тілі", density: "Мәтін көлемі",
    d_medium: "Қысқа", d_medium_s: "негізгі ойлар", d_long: "Толық", d_long_s: "түсіндірмемен", d_full: "Өте толық", d_full_s: "толық слайд",
    design: "Дизайн", design_hint: "Авто — тақырыпқа сай", font: "Қаріп", auto: "Авто", auto_s: "тақырыпқа сай",
    more: "Қосымша баптаулар", tone: "Кімге арналған / стиль",
    tone_school: "🎒 Мектеп", tone_student: "🎓 Студент", tone_business: "💼 Бизнес", tone_science: "🔬 Ғылыми", tone_creative: "🎨 Шығармашылық",
    photos: "Тақырыпқа сай суреттер", photos_s: "Әр слайдқа сәйкес фото іздейді",
    notes: "Баяндамашы жазбалары", notes_s: "Әр слайдта не айту керегі (PowerPoint заметкалары)",
    author: "Автор аты (титулдық бетке)", author_ph: "Мысалы: Айдос Мақсет, 10 «А» сынып",
    extra: "Қосымша тілек", extra_ph: "Мысалы: көбірек тарихи даталар қос, мысалдар Қазақстаннан болсын",
    eta_t: "Дайын болу уақыты", go: "Презентация жасау",
    eta_hint: "Уақыт соңғы {n} презентацияның нақты жылдамдығымен есептелді",
    eta_hint0: "Уақыт серверде өлшенеді және әр презентациядан кейін нақтыланады",
    parts_text: "мәтін", parts_images: "суреттер", parts_design: "дизайн",
    left: "Қалды", elapsed: "Өтті",
    st_outline: "Жоспар мен дизайн", st_writing: "Мәтін жазылуда", st_images: "Суреттер", st_design: "Безендіру",
    lbl_queued: "кезекте", lbl_outline: "жоспар", lbl_writing: "мәтін", lbl_images: "суреттер", lbl_design: "дизайн", lbl_done: "дайын",
    queue: "Кезекте: {n}-орын. Алдыңғы презентация біткен соң бірден басталады.",
    p_sub: "{pages} слайд · {lang} · шамамен {eta}",
    picked: "Тақырыпқа сай дизайн таңдалды · қаріп: {font}", picked_preset: "Дизайн: {theme} · қаріп: {font}",
    new: "Жаңа презентация", download: "PPTX жүктеу", r_design: "Дизайнды ауыстыру", r_font: "Қаріпті ауыстыру",
    share: "Сілтеме", copy: "Сілтемені көшіру", copied: "Сілтеме көшірілді",
    speaker: "Баяндамашыға жазба", r_meta: "{n} слайд · <b>{time}</b> ішінде дайын болды",
    designs_t: "Тақырыпқа сай дизайн",
    designs_s: "«Авто» режимінде ИИ тақырыпты талдап, түстерді, фонды, өрнекті және қаріпті өзі таңдайды. Қаласаң — дайын стильдің бірін таңда.",
    works_t: "Менің жұмыстарым", works_s: "Осы құрылғыда жасалған презентациялар (серверде 14 күн сақталады)",
    works_empty: "Әзірге бос. Алғашқы презентацияңды жаса!", open: "Ашу",
    how_t: "Қалай жұмыс істейді?", how_s: "Бір-екі минутта — дайын презентация.",
    s1: "Тақырыпты жаз", s1p: "Кез келген тақырып: сабақ, баяндама, бизнес, ғылым.",
    s2: "Баптауларды таңда", s2p: "Слайд саны, тіл, мәтін көлемі, дизайн мен қаріп.",
    s3: "ИИ жасайды", s3p: "Жоспар, толық мәтін, суреттер және дизайн — нақты таймермен.",
    s4: "Жүктеп ал", s4p: "Дайын PPTX-ті PowerPoint, Keynote не Google Slides-та аш.",
    faq_t: "Жиі қойылатын сұрақтар", foot: "Тақырыптан — дайын презентацияға",
    min: "мин", sec: "сек",
    err_auth: "Сервер бапталмаған: ИИ кілті қате не жоқ.", err_busy: "ИИ қазір бос емес, бір минуттан соң қайталаңыз.",
    err_network: "ИИ-мен байланыс үзілді. Қайталап көріңіз.", err_refusal: "Бұл тақырыпқа презентация жасай алмаймын. Басқа тақырып жазып көріңіз.",
    err_failed: "Қате шықты. Қайталап көріңіз.", err_restart: "Сервер қайта қосылды — презентацияны қайта жасаңыз.",
    err_rate_limit: "Сағатына шектеу бар. Сәлден соң қайталаңыз.", err_not_configured: "Сайт әлі бапталуда: әкімші ANTHROPIC_API_KEY қосуы керек.",
    err_bad_params: "Баптаулар қате.", err_bad_request: "Сұраныс қате. Тақырыпты өзгертіп көріңіз.",
    err_daily_limit: "Бүгінгі тегін лимит таусылды (Gemini). Ертең қайталаңыз.",
    err_quota: "ИИ кілтінің балансы таусылған не толтырылмаған. Әкімші балансты толтыруы не тегін GEMINI_API_KEY қосуы керек.",
    err_topic: "Тақырыпты жазыңыз (кемінде 3 әріп).", err_not_found: "Презентация табылмады (мерзімі өткен болуы мүмкін).",
    retry: "Қайта көру",
    examples: ["Ғарышты игеру", "Наурыз мейрамы", "Жасанды интеллект", "Абай Құнанбайұлы", "Климаттың өзгеруі", "Қазақ хандығы", "Салауатты өмір салты"],
    faq: [
      ["Қанша уақытта дайын болады?", "Әр слайд санының қасында нақты уақыт жазылған. Ол серверде соңғы презентациялардың шын жылдамдығымен есептеледі, ал жасау кезінде таймер секунд сайын жаңарып, қанша уақыт қалғанын көрсетеді."],
      ["Дизайн тақырыпқа қалай сай келеді?", "«Авто» режимінде ИИ алдымен тақырыпты талдайды: ғарышқа — қою көк пен неон, тарихқа — сепия мен алтын, табиғатқа — жасыл түстер, мектепке — ашық әрі жарқын стиль. Қаріп пен өрнек те соған қарай таңдалады."],
      ["Мәтін қаншалықты толық болады?", "«Толық» режимінде әр слайдта кіріспе сөйлем және түсіндірмесі бар толық сөйлемдер болады. «Өте толық» — оқулық бетіндей толық слайд. Мәтін көп болса да қаріп өлшемі автоматты түрде сыйғызылады."],
      ["Файлды өзгертуге бола ма?", "Иә, бұл кәдімгі .pptx: мәтінді, суретті, түсті PowerPoint-та еркін өзгерте аласыз. Баяндамашы жазбалары да бар."],
      ["Суреттер қайдан алынады?", "Ашық фотобанктерден (Openverse, Wikimedia Commons, Pexels) тақырыпқа сай таңдалады. Сурет табылмаса — дизайнға сай абстракт бейне қойылады."],
      ["Дизайнды кейін ауыстыруға бола ма?", "Иә! Дайын болған соң дизайн мен қаріпті бір батырмамен ауыстырып, қайта жүктей аласыз — мәтін мен суреттер сақталады."],
    ],
    autoex: [
      { t: "Ғарышты игеру", d: "қою көк + неон · геометрия · Segoe UI", p: ["0B1D3A", "1A0B3A", "22D3EE", "A855F7"] },
      { t: "Абай Құнанбайұлы", d: "сепия + алтын · сызықтар · Times New Roman", p: ["2A1A12", "4A2418", "D4AF37", "F5E6B3"] },
      { t: "Наурыз мейрамы", d: "көгілдір + алтын · жұмсақ пішіндер · Cambria", p: ["0E5E6F", "1B3B4F", "FFC93C", "40E0D0"] },
    ],
    sample_title: "Тақырып атауы", sample_lead: "Мұнда слайдтың негізгі ойы түсінікті сөйлеммен жазылады.",
    sample_b: ["Бірінші: толық сөйлеммен түсіндірме", "Екінші: нақты мысал мен дерек", "Үшінші: қорытынды ой"],
  },
  ru: {
    nav_create: "Создать", nav_designs: "Дизайны", nav_works: "Мои работы", nav_how: "Как это работает", nav_faq: "Вопросы",
    badge: "ИИ-генератор презентаций · на казахском и русском",
    h1: "Напиши тему — получи <em>готовую презентацию</em>",
    sub: "ZhubiSlide подбирает дизайн под тему, пишет полный и понятный текст, добавляет фото и отдаёт файл PowerPoint.",
    f1: "<b>5–25</b> слайдов", f2: "Дизайн <b>под тему</b>", f3: "<b>Точное</b> время готовности", f4: "Файл <b>.PPTX</b>",
    topic: "Тема", topic_ph: "Например: Образование Казахского ханства",
    pages: "Количество слайдов", pages_hint: "рядом — время готовности",
    slang: "Язык презентации", density: "Объём текста",
    d_medium: "Кратко", d_medium_s: "главные мысли", d_long: "Подробно", d_long_s: "с пояснениями", d_full: "Максимум", d_full_s: "полный слайд",
    design: "Дизайн", design_hint: "Авто — под тему", font: "Шрифт", auto: "Авто", auto_s: "под тему",
    more: "Дополнительные настройки", tone: "Для кого / стиль",
    tone_school: "🎒 Школа", tone_student: "🎓 Студент", tone_business: "💼 Бизнес", tone_science: "🔬 Научный", tone_creative: "🎨 Креативный",
    photos: "Фото по теме", photos_s: "Подбирает фото к каждому слайду",
    notes: "Заметки докладчика", notes_s: "Что говорить на каждом слайде (заметки PowerPoint)",
    author: "Имя автора (на титульный слайд)", author_ph: "Например: Айдос Максет, 10 «А» класс",
    extra: "Дополнительные пожелания", extra_ph: "Например: добавь больше дат, примеры из Казахстана",
    eta_t: "Будет готово через", go: "Создать презентацию",
    eta_hint: "Время рассчитано по реальной скорости последних {n} презентаций",
    eta_hint0: "Время измеряется на сервере и уточняется после каждой презентации",
    parts_text: "текст", parts_images: "фото", parts_design: "дизайн",
    left: "Осталось", elapsed: "Прошло",
    st_outline: "План и дизайн", st_writing: "Пишется текст", st_images: "Фото", st_design: "Оформление",
    lbl_queued: "в очереди", lbl_outline: "план", lbl_writing: "текст", lbl_images: "фото", lbl_design: "дизайн", lbl_done: "готово",
    queue: "В очереди: {n}-е место. Начнётся сразу после предыдущей презентации.",
    p_sub: "{pages} слайдов · {lang} · примерно {eta}",
    picked: "Подобран дизайн под тему · шрифт: {font}", picked_preset: "Дизайн: {theme} · шрифт: {font}",
    new: "Новая презентация", download: "Скачать PPTX", r_design: "Сменить дизайн", r_font: "Сменить шрифт",
    share: "Ссылка", copy: "Скопировать ссылку", copied: "Ссылка скопирована",
    speaker: "Заметка докладчика", r_meta: "{n} слайдов · готово за <b>{time}</b>",
    designs_t: "Дизайн под вашу тему",
    designs_s: "В режиме «Авто» ИИ анализирует тему и сам подбирает цвета, фон, орнамент и шрифт. Или выберите готовый стиль.",
    works_t: "Мои работы", works_s: "Презентации, созданные на этом устройстве (на сервере хранятся 14 дней)",
    works_empty: "Пока пусто. Создайте первую презентацию!", open: "Открыть",
    how_t: "Как это работает?", how_s: "Готовая презентация за пару минут.",
    s1: "Напиши тему", s1p: "Любая тема: урок, доклад, бизнес, наука.",
    s2: "Выбери настройки", s2p: "Количество слайдов, язык, объём текста, дизайн и шрифт.",
    s3: "ИИ создаёт", s3p: "План, полный текст, фото и дизайн — с точным таймером.",
    s4: "Скачай", s4p: "Открой PPTX в PowerPoint, Keynote или Google Slides.",
    faq_t: "Частые вопросы", foot: "От темы — к готовой презентации",
    min: "мин", sec: "сек",
    err_auth: "Сервер не настроен: ключ ИИ неверный или отсутствует.", err_busy: "ИИ сейчас занят, повторите через минуту.",
    err_network: "Связь с ИИ прервалась. Попробуйте ещё раз.", err_refusal: "Не могу сделать презентацию на эту тему. Попробуйте другую.",
    err_failed: "Произошла ошибка. Попробуйте ещё раз.", err_restart: "Сервер перезапустился — создайте презентацию заново.",
    err_rate_limit: "Лимит в час исчерпан. Попробуйте немного позже.", err_not_configured: "Сайт ещё настраивается: администратору нужно добавить ANTHROPIC_API_KEY.",
    err_bad_params: "Неверные настройки.", err_bad_request: "Ошибка запроса. Попробуйте изменить тему.",
    err_daily_limit: "Бесплатный лимит на сегодня исчерпан (Gemini). Попробуйте завтра.",
    err_quota: "Баланс ключа ИИ пуст или не пополнен. Администратору нужно пополнить баланс или добавить бесплатный GEMINI_API_KEY.",
    err_topic: "Напишите тему (минимум 3 буквы).", err_not_found: "Презентация не найдена (возможно, срок хранения истёк).",
    retry: "Попробовать снова",
    examples: ["Освоение космоса", "Праздник Наурыз", "Искусственный интеллект", "Абай Кунанбаев", "Изменение климата", "Казахское ханство", "Здоровый образ жизни"],
    faq: [
      ["Сколько времени занимает?", "Рядом с каждым количеством слайдов указано точное время. Оно рассчитывается на сервере по реальной скорости последних презентаций, а во время создания таймер обновляется каждую секунду."],
      ["Как дизайн подбирается под тему?", "В режиме «Авто» ИИ сначала анализирует тему: космос — тёмно-синий и неон, история — сепия и золото, природа — зелёные тона, школа — светлый и яркий стиль. Шрифт и орнамент тоже подбираются под тему."],
      ["Насколько подробный текст?", "В режиме «Подробно» на каждом слайде вводное предложение и полные предложения с пояснениями. «Максимум» — полный слайд, как страница учебника. Даже при большом тексте размер шрифта подбирается автоматически."],
      ["Можно ли редактировать файл?", "Да, это обычный .pptx: текст, фото и цвета можно свободно менять в PowerPoint. Заметки докладчика тоже есть."],
      ["Откуда берутся фото?", "Из открытых фотобанков (Openverse, Wikimedia Commons, Pexels) по теме слайда. Если фото не найдено — ставится абстрактное изображение в стиле дизайна."],
      ["Можно ли потом сменить дизайн?", "Да! После готовности дизайн и шрифт меняются одной кнопкой и скачиваются заново — текст и фото сохраняются."],
    ],
    autoex: [
      { t: "Освоение космоса", d: "тёмно-синий + неон · геометрия · Segoe UI", p: ["0B1D3A", "1A0B3A", "22D3EE", "A855F7"] },
      { t: "Абай Кунанбаев", d: "сепия + золото · линии · Times New Roman", p: ["2A1A12", "4A2418", "D4AF37", "F5E6B3"] },
      { t: "Праздник Наурыз", d: "бирюза + золото · мягкие формы · Cambria", p: ["0E5E6F", "1B3B4F", "FFC93C", "40E0D0"] },
    ],
    sample_title: "Название темы", sample_lead: "Здесь главная мысль слайда написана понятным предложением.",
    sample_b: ["Первое: пояснение полным предложением", "Второе: конкретный пример и факт", "Третье: вывод"],
  },
};
const LANG_NAMES = { kk: "Қазақша", ru: "Русский" };
const TONES = ["school", "student", "business", "science", "creative"];

let UI = store.get("zs_ui", (navigator.language || "").startsWith("ru") ? "ru" : "kk");
if (!I18N[UI]) UI = "kk";
const tr = (k, vars = {}) => String(I18N[UI][k] ?? I18N.kk[k] ?? k).replace(/\{(\w+)\}/g, (_, v) => vars[v] ?? "");

function fmtClock(s) {
  s = Math.max(0, Math.round(s));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
function fmtHuman(s) {
  s = Math.max(1, Math.round(s));
  const m = Math.floor(s / 60), r = s % 60;
  if (!m) return `${r} ${tr("sec")}`;
  return r ? `${m} ${tr("min")} ${r} ${tr("sec")}` : `${m} ${tr("min")}`;
}
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("on");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => el.classList.remove("on"), 2400);
}

/* ───────────────────────── colours ───────────────────────── */
function lum(hex) {
  const c = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
const contrast = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const onColor = (hex) => (contrast("FFFFFF", hex) >= contrast("111827", hex) ? "#FFFFFF" : "#111827");
const shadeOf = (t) => (t.dark ? t.bg[0] : "0F172A");

/* ───────────────────────── slide renderer (mirrors app/builder.py) ───────────────────────── */
const X0 = 0.75, X1 = 12.58, TOP = 2.0, BOTTOM = 6.75;
const IN = (v) => `${(v * 7.5).toFixed(3)}cqw`;
const PT = (v) => `${((v * 7.5) / 72).toFixed(3)}cqw`;
const box = (x, y, w, h) => `left:${IN(x)};top:${IN(y)};width:${IN(w)};height:${IN(h)};`;

function fitBox(x, y, w, h, html, max, min, { anchor = "top", align = "left", bold = false, italic = false, color = "", group = "", extra = "" } = {}) {
  const just = anchor === "bottom" ? "flex-end" : anchor === "middle" ? "center" : "flex-start";
  return `<div class="abs fit" data-max="${max}" data-min="${min}" ${group ? `data-group="${group}"` : ""} style="${box(x, y, w, h)}display:flex;flex-direction:column;justify-content:${just};text-align:${align};${bold ? "font-weight:700;" : ""}${italic ? "font-style:italic;" : ""}${color ? `color:${color};` : ""}${extra}"><div class="fi">${html}</div></div>`;
}
function bulletsHtml(items, accent) {
  return `<ul style="--bul:${accent}">${items.filter(Boolean).map((it) => {
    const i = it.indexOf(":");
    const head = i > 1 && i <= 45 && it.slice(i + 1).trim() ? it.slice(0, i + 1) : "";
    return `<li>${head ? `<b>${esc(head)}</b>${esc(it.slice(i + 1))}` : esc(it)}</li>`;
  }).join("")}</ul>`;
}
function bodyHtml(lead, items, accent) {
  return `${lead ? `<div class="lead">${esc(lead)}</div>` : ""}${bulletsHtml(items || [], accent)}`;
}
function rectHtml(x, y, w, h, color, { op = 1, radius = 0, round = false, extra = "" } = {}) {
  return `<div class="abs" style="${box(x, y, w, h)}background:#${color};opacity:${op};border-radius:${round ? "50%" : IN(radius)};${extra}"></div>`;
}
function heading(t, title, x = X0, w = X1 - X0, max = 32) {
  return fitBox(x, 0.5, w, 1.12, esc(title), max, 20, { anchor: "bottom", bold: true, extra: "line-height:1.02;" })
    + rectHtml(x, 1.74, 0.9, 0.07, t.accent, { radius: 0.04 }) + rectHtml(x + 1.0, 1.74, 0.25, 0.07, t.accent2, { radius: 0.04 });
}
function decor(t, seed) {
  const op = t.dark ? 0.16 : 0.11;
  const [a, b] = seed % 2 ? [t.accent, t.accent2] : [t.accent2, t.accent];
  const p = t.pattern || "blobs";
  if (p === "geometric") {
    const hex = "clip-path:polygon(25% 5%,75% 5%,100% 50%,75% 95%,25% 95%,0 50%);";
    return rectHtml(11.6, -1.1, 2.6, 2.6, b, { op, extra: hex + `transform:rotate(${15 * (seed % 3)}deg);` })
      + rectHtml(12.5, 0.8, 1.3, 1.3, a, { op, extra: "clip-path:polygon(50% 0,100% 50%,50% 100%,0 50%);" })
      + rectHtml(-1.0, 6.2, 2.2, 2.2, b, { op, extra: hex });
  }
  if (p === "lines") {
    let s = "";
    for (let i = 0; i < 4; i++) s += rectHtml(12.75 + i * 0.16, -0.5, 0.04, 8.5, a, { op: op * (1.8 - i * 0.35) });
    return s + rectHtml(0, 7.36, 13.333, 0.05, b, { op: op * 2 });
  }
  if (p === "dots") {
    let s = "";
    for (let r = 0; r < 3; r++) for (let c = 0; c < 5; c++) s += rectHtml(11.25 + c * 0.32, 0.22 + r * 0.32, 0.1, 0.1, (r + c) % 2 ? a : b, { op: op * 2.4, round: true });
    return s + rectHtml(-1.4, 6.1, 2.6, 2.6, b, { op: op * 0.8, round: true });
  }
  return seed % 2
    ? rectHtml(11.2, -2.0, 3.8, 3.8, a, { op, round: true }) + rectHtml(-1.5, 6.0, 3.0, 3.0, b, { op: op * 0.8, round: true })
    : rectHtml(-1.8, -2.0, 3.8, 3.8, a, { op: op * 0.8, round: true }) + rectHtml(11.4, 5.9, 3.4, 3.4, b, { op, round: true });
}
function footer(title, n, total) {
  return `<div class="foot" style="left:${IN(X0)};width:${IN(8)}">${esc(title)}</div><div class="foot" style="left:${IN(X1 - 1.6)};width:${IN(1.6)};text-align:right">${String(n).padStart(2, "0")} / ${String(total).padStart(2, "0")}</div>`;
}
function photo(x, y, w, h, url, { radius = 0.3, dark = 1, blur = 0 } = {}) {
  if (!url) return "";
  const f = `${dark !== 1 ? `brightness(${dark})` : ""} ${blur ? `blur(${blur}cqw)` : ""}`.trim();
  return `<div class="ph" style="${box(x, y, w, h)}background-image:url('${url}');border-radius:${IN(radius)};${f ? `filter:${f};` : ""}${blur ? "transform:scale(1.08);" : ""}"></div>`;
}
function panel(t, x, y, w, h, border = "") {
  return `<div class="panel" style="${box(x, y, w, h)}${border ? `border:0.1cqw solid #${border};` : ""}opacity:${t.dark ? 0.88 : 0.95}"></div>`;
}
function leadLine(t, lead, y = TOP) {
  if (!lead) return { html: "", y };
  const lines = Math.min(2, Math.ceil(lead.length / 105));
  const h = Math.min(0.95, lines * 0.32 + 0.05);
  return { html: fitBox(X0, y, X1 - X0, h, esc(lead), 17, 11, { color: `#${t.muted}`, extra: "line-height:1.3;" }), y: y + h + 0.22 };
}

const L = {
  cover(t, deck, img, author) {
    const meta = [author, new Date().getFullYear()].filter(Boolean).join(" · ");
    return photo(0, 0, 13.333, 7.5, img, { radius: 0, dark: 0.55 })
      + rectHtml(0, 0, 8.6, 7.5, shadeOf(t), { op: 0.6 }) + rectHtml(X0, 1.75, 0.12, 3.6, t.accent)
      + fitBox(1.2, 1.2, 7.1, 2.75, esc(deck.title), 48, 26, { anchor: "bottom", bold: true, color: "#fff", extra: "line-height:0.98;" })
      + fitBox(1.2, 4.15, 7.0, 1.35, esc(deck.subtitle), 20, 13, { color: "#E5E7EB", extra: "line-height:1.3;" })
      + fitBox(1.2, 6.25, 7, 0.4, esc(meta), 14, 10, { bold: true, color: `#${t.dark ? t.accent2 : "FFFFFF"}` });
  },
  side(t, s, img, right) {
    const iw = 4.55, ix = right ? 13.333 - 0.6 - iw : 0.6, tx = right ? X0 : 0.6 + iw + 0.5, tw = right ? ix - 0.45 - tx : X1 - tx;
    return photo(ix, 0.6, iw, 6.1, img) + rectHtml(ix + (right ? 0.3 : iw - 1.0), 6.32, 0.7, 0.7, t.accent, { round: true })
      + heading(t, s.title, tx, tw, 30)
      + fitBox(tx, TOP, tw, BOTTOM - TOP, bodyHtml(s.lead, s.bullets, `#${t.accent}`), 20, 10.5);
  },
  article(t, s) {
    let h = heading(t, s.title), px = X0;
    let items = s.bullets || [];
    if (s.lead && items.length) {
      h += rectHtml(X0, TOP + 0.05, 0.09, BOTTOM - TOP - 0.1, t.accent)
        + fitBox(X0 + 0.35, TOP, 3.85, BOTTOM - TOP, esc(s.lead), 22, 12, { anchor: "middle", extra: "line-height:1.3;" });
      px = X0 + 4.55;
    } else if (!items.length) items = [s.lead];
    return h + panel(t, px, TOP - 0.1, X1 - px, BOTTOM - TOP + 0.2)
      + fitBox(px + 0.4, TOP + 0.2, X1 - px - 0.8, BOTTOM - TOP - 0.4, bulletsHtml(items, `#${t.accent}`), 19, 10.5, { anchor: "middle" });
  },
  cards(t, s, gid) {
    let h = heading(t, s.title);
    const ll = leadLine(t, s.lead); h += ll.html;
    const items = (s.bullets || []).slice(0, 4);
    if (!items.length) items.push(s.lead || s.title);
    const n = items.length, gap = 0.3, cw = (X1 - X0 - gap * (n - 1)) / n, top = ll.y, ch = BOTTOM - top;
    items.forEach((it, i) => {
      const x = X0 + (cw + gap) * i, color = i % 2 ? t.accent2 : t.accent;
      const k = it.indexOf(":"), head = k > 0 && k < 70 && it.slice(k + 1).trim() ? it.slice(0, k).trim() : "", rest = head ? it.slice(k + 1).trim() : it;
      h += panel(t, x, top, cw, ch, color) + rectHtml(x + 0.25, top, cw - 0.5, 0.07, color)
        + `<div class="circle" style="${box(x + 0.3, top + 0.35, 0.62, 0.62)}background:#${color};color:${onColor(color)};font-size:${PT(14)}">${String(i + 1).padStart(2, "0")}</div>`;
      if (head) h += fitBox(x + 1.05, top + 0.26, cw - 1.35, 0.8, esc(head), 18, 10, { anchor: "middle", bold: true, group: gid + "h", extra: "line-height:1.05;" });
      h += fitBox(x + 0.3, top + 1.2, cw - 0.6, ch - 1.35, esc(rest), n <= 3 ? 19 : 18, 10, { group: gid + "b", color: `#${head ? t.muted : t.text}`, extra: "line-height:1.3;" });
    });
    return h;
  },
  stats(t, s, gid) {
    const stats = (s.stats || []).slice(0, 4);
    if (!stats.length) return L.cards(t, s, gid);
    let h = heading(t, s.title);
    const ll = leadLine(t, s.lead); h += ll.html;
    const n = stats.length, gap = 0.3, cw = (X1 - X0 - gap * (n - 1)) / n, top = ll.y;
    const rest = (s.bullets || []).filter(Boolean).slice(0, 3);
    const sh = rest.join("").length > 220 ? 2.15 : 2.6, vh = sh * 0.5;
    stats.forEach((st, i) => {
      const x = X0 + (cw + gap) * i, color = i % 2 ? t.accent2 : t.accent;
      h += panel(t, x, top, cw, sh) + rectHtml(x + 0.3, top + sh - 0.07, cw - 0.6, 0.07, color)
        + fitBox(x + 0.2, top + 0.15, cw - 0.4, vh, esc(st.value), 54, 22, { anchor: "middle", align: "center", bold: true, color: `#${color}`, extra: "line-height:1;" })
        + fitBox(x + 0.25, top + 0.3 + vh, cw - 0.5, sh - vh - 0.45, esc(st.label), 17, 10.5, { align: "center", extra: "line-height:1.2;" });
    });
    if (rest.length) { const y = top + sh + 0.35; h += fitBox(X0, y, X1 - X0, BOTTOM - y, bulletsHtml(rest, `#${t.accent}`), 19, 10.5); }
    return h;
  },
  quote(t, s, img) {
    let h = photo(0, 0, 13.333, 7.5, img, { radius: 0, dark: 0.4 }) + rectHtml(0, 0, 13.333, 7.5, shadeOf(t), { op: 0.4 })
      + `<div class="abs" style="${box(1.1, 0.45, 2, 1.6)}font-size:${PT(140)};line-height:1;font-weight:700;color:#${t.dark ? t.accent : t.accent2}">“</div>`
      + fitBox(1.8, 1.45, 9.9, 3.1, esc(s.quote || s.title), 34, 18, { anchor: "middle", italic: true, color: "#fff", extra: "line-height:1.3;" });
    if (s.quote_author) h += rectHtml(1.8, 4.95, 0.6, 0.06, t.accent) + fitBox(2.6, 4.75, 9, 0.5, esc(s.quote_author), 18, 12, { anchor: "middle", bold: true, color: "#fff" });
    if (s.lead) h += fitBox(1.8, 5.5, 9.9, 1.25, esc(s.lead), 17, 11, { color: "#E5E7EB", extra: "line-height:1.3;" });
    return h;
  },
  two(t, s, gid) {
    let h = heading(t, s.title);
    const ll = leadLine(t, s.lead); h += ll.html;
    const top = ll.y, cw = (X1 - X0 - 0.4) / 2, hh = 0.75, bh = BOTTOM - top - hh - 0.45;
    [[s.left_title, s.bullets, t.accent], [s.right_title, s.right_bullets, t.accent2]].forEach(([title, items, color], i) => {
      const x = X0 + (cw + 0.4) * i;
      h += panel(t, x, top, cw, BOTTOM - top) + rectHtml(x, top, cw, hh, color, { radius: 0.19 })
        + fitBox(x + 0.35, top, cw - 0.7, hh, esc(title || ""), 20, 12, { anchor: "middle", bold: true, color: onColor(color), extra: "line-height:1.05;" })
        + fitBox(x + 0.35, top + hh + 0.25, cw - 0.7, bh, bulletsHtml(items || [], `#${color}`), 18, 10, { group: gid + "c" });
    });
    return h + `<div class="circle" style="${box(6.265, top + (BOTTOM - top) / 2 - 0.4, 0.8, 0.8)}background:#${t.bg[1]};border:0.2cqw solid #${t.accent};font-size:${PT(14)}">VS</div>`;
  },
  timeline(t, s, gid) {
    const items = (s.bullets || []).filter(Boolean).slice(0, 6);
    if (!items.length) return L.article(t, s);
    let h = heading(t, s.title);
    const ll = leadLine(t, s.lead); h += ll.html;
    const top = ll.y, n = items.length, step = (X1 - X0) / n, bw = step - 0.2, lineY = top + 0.78, boxTop = lineY + 0.42, boxH = BOTTOM - boxTop;
    h += rectHtml(X0, lineY, X1 - X0, 0.05, t.muted, { op: 0.5 });
    items.forEach((it, i) => {
      const k = it.indexOf(":"), head = k > 0 && k <= 30 ? it.slice(0, k).trim() : String(i + 1), rest = k > 0 && k <= 30 ? it.slice(k + 1).trim() : it;
      const cx = X0 + step * i + step / 2, color = i % 2 ? t.accent2 : t.accent;
      h += `<div class="circle" style="${box(cx - 0.2, lineY - 0.18, 0.4, 0.4)}background:#${color};border:0.25cqw solid #${t.bg[0]}"></div>`
        + fitBox(cx - bw / 2, top, bw, 0.6, esc(head), 20, 11, { anchor: "bottom", align: "center", bold: true, color: `#${color}`, group: gid + "h" })
        + panel(t, cx - bw / 2, boxTop, bw, boxH)
        + fitBox(cx - bw / 2 + 0.15, boxTop + 0.15, bw - 0.3, boxH - 0.3, esc(rest), n <= 4 ? 17 : 16, 10, { align: "center", group: gid + "b", extra: "line-height:1.3;" });
    });
    return h;
  },
  thanks(t, deck, img) {
    return photo(0, 0, 13.333, 7.5, img, { radius: 0, dark: 0.45, blur: 1.2 }) + rectHtml(0, 0, 13.333, 7.5, shadeOf(t), { op: 0.35 })
      + fitBox(1, 2.1, 11.33, 1.8, esc(deck.thanks || "Рахмет!"), 54, 30, { anchor: "middle", align: "center", bold: true, color: "#fff" })
      + rectHtml(6.07, 4.05, 1.2, 0.08, t.accent, { radius: 0.04 })
      + fitBox(1.5, 4.35, 10.33, 1.0, esc(deck.title), 20, 13, { align: "center", color: "#E5E7EB" });
  },
};

const IMAGE_LAYOUTS = new Set(["image_right", "image_left", "quote"]);

/** One slide as HTML. idx: -1 cover, 0..n-1 content, n thanks. */
function slideHtml(ctx, idx) {
  const { deck, theme: t } = ctx;
  const n = deck.slides.length, total = n + 2;
  const vars = `--s-bg1:#${t.bg[0]};--s-bg2:#${t.bg[1]};--s-text:#${t.text};--s-muted:#${t.muted};--s-accent:#${t.accent};--s-accent2:#${t.accent2};--s-surface:#${t.surface};--s-font:${ctx.fontCss};--angle:${t.angle || 135}deg`;
  let inner;
  if (idx < 0) inner = L.cover(t, deck, ctx.img("cover"), ctx.author);
  else if (idx >= n) inner = L.thanks(t, deck, ctx.img("cover"));
  else {
    const s = deck.slides[idx];
    let layout = s.layout;
    const img = ctx.img(String(idx));
    if (IMAGE_LAYOUTS.has(layout) && !img) layout = "article";
    const gid = `g${idx}`;
    inner = layout === "quote" ? "" : decor(t, idx);
    inner += layout === "image_right" ? L.side(t, s, img, true)
      : layout === "image_left" ? L.side(t, s, img, false)
      : layout === "quote" ? L.quote(t, s, img)
      : layout === "stats" ? L.stats(t, s, gid)
      : layout === "two_column" ? L.two(t, s, gid)
      : layout === "timeline" ? L.timeline(t, s, gid)
      : layout === "cards" ? L.cards(t, s, gid)
      : L.article(t, s);
    if (layout !== "quote") inner += footer(deck.title, idx + 2, total);
  }
  return `<div class="slide ${t.dark ? "dark" : ""}" style="${vars}">${inner}</div>`;
}

/** Shrinks every .fit box until its content fits (same idea as fit() in the PPTX builder). */
function fitAll(root) {
  const sizes = new Map();
  $$(".fit", root).forEach((el) => {
    const inner = el.firstElementChild, max = +el.dataset.max, min = +el.dataset.min || 9;
    let s = max, guard = 0;
    el.style.fontSize = PT(s);
    while (s > min && guard++ < 90 && (inner.offsetHeight > el.clientHeight + 1 || inner.scrollWidth > el.clientWidth + 1)) {
      s -= 0.5;
      el.style.fontSize = PT(s);
    }
    const g = el.dataset.group;
    if (g) sizes.set(g, Math.min(sizes.get(g) ?? s, s));
  });
  $$(".fit[data-group]", root).forEach((el) => { el.style.fontSize = PT(sizes.get(el.dataset.group)); });
}

/* ───────────────────────── state ───────────────────────── */
const S = {
  meta: null,
  form: Object.assign({ pages: 10, lang: UI, density: "long", theme: "auto", font: "auto", tone: "student", photos: true, notes: true }, store.get("zs_form", {})),
  job: null, poll: null, tick: null, lastPoll: 0,
  result: null, cur: 0, rTheme: "auto", rFont: "auto",
};

function saveForm() {
  const { pages, lang, density, theme, font, tone, photos, notes } = S.form;
  store.set("zs_form", { pages, lang, density, theme, font, tone, photos, notes });
}

/* ───────────────────────── i18n apply ───────────────────────── */
function applyI18n() {
  document.documentElement.lang = UI;
  $$("[data-i18n]").forEach((el) => { el.textContent = tr(el.dataset.i18n); });
  $$("[data-i18n-html]").forEach((el) => { el.innerHTML = tr(el.dataset.i18nHtml); });
  $$("[data-i18n-ph]").forEach((el) => { el.placeholder = tr(el.dataset.i18nPh); });
  $$("[data-ui]").forEach((b) => b.classList.toggle("on", b.dataset.ui === UI));
  $("#examples").innerHTML = I18N[UI].examples.map((e) => `<button type="button">${esc(e)}</button>`).join("");
  $("#faq-list").innerHTML = I18N[UI].faq.map(([q, a]) => `<details><summary>${esc(q)}</summary><p>${esc(a)}</p></details>`).join("");
  $("#tones").innerHTML = TONES.map((k) => `<button type="button" class="chip ${S.form.tone === k ? "on" : ""}" data-v="${k}">${tr("tone_" + k)}</button>`).join("");
  if (S.meta) { renderChoices(); renderGallery(); updateEta(); }
  renderWorks();
  if (S.job) renderProgress(S.job);
  if (S.result) renderResultHead();
}

/* ───────────────────────── form ───────────────────────── */
function themeName(key) {
  if (key === "auto") return tr("auto");
  const th = S.meta?.themes[key];
  return th ? th.name[UI] || th.name.kk : key;
}
function themeButton(key, on) {
  if (key === "auto") return `<button type="button" class="theme auto ${on ? "on" : ""}" data-v="auto"><div class="sw">✨</div><span>${tr("auto")}</span></button>`;
  const th = S.meta.themes[key];
  return `<button type="button" class="theme ${on ? "on" : ""}" data-v="${key}"><div class="sw" style="background:linear-gradient(135deg,#${th.bg[0]},#${th.bg[1]});--a:#${th.accent};--a2:#${th.accent2}"></div><span>${esc(themeName(key))}</span></button>`;
}
function renderChoices() {
  const m = S.meta, f = S.form;
  $("#pages").innerHTML = m.pages.map((p) => {
    const e = m.estimates[f.density][p][f.photos ? "1" : "0"].seconds;
    return `<button type="button" class="chip ${f.pages === p ? "on" : ""}" data-v="${p}"><b>${p}</b><small>≈ ${fmtClock(e)}</small></button>`;
  }).join("");
  $$("#slang .chip").forEach((b) => b.classList.toggle("on", b.dataset.v === f.lang));
  $$("#density .chip").forEach((b) => b.classList.toggle("on", b.dataset.v === f.density));
  $("#themes").innerHTML = ["auto", ...Object.keys(m.themes)].map((k) => themeButton(k, f.theme === k)).join("");
  $("#fonts").innerHTML = `<button type="button" class="font ${f.font === "auto" ? "on" : ""}" data-v="auto"><b>✨ Aa</b><small>${tr("auto")} · ${tr("auto_s")}</small></button>`
    + Object.entries(m.fonts).map(([name, css]) => `<button type="button" class="font ${f.font === name ? "on" : ""}" data-v="${esc(name)}"><b style="font-family:${esc(css)}">Аа Әә</b><small>${esc(name)}</small></button>`).join("");
  $("#photos").checked = f.photos;
  $("#notes").checked = f.notes;
}
function updateEta() {
  const m = S.meta, f = S.form;
  if (!m) return;
  const e = m.estimates[f.density][f.pages][f.photos ? "1" : "0"];
  $("#eta-v").textContent = `≈ ${fmtHuman(e.seconds)}`;
  $("#eta-parts").innerHTML = [["parts_text", e.parts.text], ["parts_images", e.parts.images], ["parts_design", e.parts.design]]
    .map(([k, v]) => `<span>${tr(k)} ${fmtClock(v)}</span>`).join("");
  $("#eta-hint").textContent = m.learned_from ? tr("eta_hint", { n: Math.min(m.learned_from, 99) }) : tr("eta_hint0");
}
function showAlert(msg, warn = false) {
  $("#form-alert").innerHTML = msg ? `<div class="alert ${warn ? "warn" : ""}">${esc(msg)}</div>` : "";
}

function bindForm() {
  const topic = $("#topic");
  topic.value = store.get("zs_topic", "");
  const count = () => { $("#topic-count").textContent = `${topic.value.length} / 300`; store.set("zs_topic", topic.value); };
  topic.addEventListener("input", count);
  count();
  $("#examples").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { topic.value = b.textContent; count(); topic.focus(); } });
  const pick = (sel, key, cast = (v) => v) => $(sel).addEventListener("click", (e) => {
    const b = e.target.closest("[data-v]");
    if (!b) return;
    S.form[key] = cast(b.dataset.v);
    saveForm(); renderChoices(); updateEta();
    if (key === "tone") $$("#tones .chip").forEach((c) => c.classList.toggle("on", c.dataset.v === S.form.tone));
  });
  pick("#pages", "pages", Number); pick("#slang", "lang"); pick("#density", "density");
  pick("#themes", "theme"); pick("#fonts", "font"); pick("#tones", "tone");
  $("#photos").addEventListener("change", (e) => { S.form.photos = e.target.checked; saveForm(); renderChoices(); updateEta(); });
  $("#notes").addEventListener("change", (e) => { S.form.notes = e.target.checked; saveForm(); });
  $("#author").value = store.get("zs_author", "");
  $("#author").addEventListener("input", (e) => store.set("zs_author", e.target.value));
  $("#go").addEventListener("click", submit);
}

async function submit() {
  const topic = $("#topic").value.trim();
  if (topic.length < 3) { showAlert(tr("err_topic")); $("#topic").focus(); return; }
  showAlert("");
  const btn = $("#go");
  btn.disabled = true;
  try {
    const f = S.form;
    const res = await fetch("/api/jobs", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, pages: f.pages, lang: f.lang, theme: f.theme, font: f.font, tone: f.tone, density: f.density,
        photos: f.photos, notes: f.notes, author: $("#author").value.trim(), extra: $("#extra").value.trim() }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { showAlert(tr("err_" + (data.error || "failed"))); return; }
    addWork(data);
    location.hash = `#/p/${data.id}`;
  } catch {
    showAlert(tr("err_network"));
  } finally {
    btn.disabled = false;
  }
}

/* ───────────────────────── panes & routing ───────────────────────── */
function showPane(name) {
  $$(".pane").forEach((p) => p.classList.toggle("on", p.id === `pane-${name}`));
}
function route() {
  const m = location.hash.match(/^#\/p\/([a-f0-9]{32})$/);
  if (!m) return;                       // ordinary anchors (#designs, #faq…) never interrupt a running job
  if (S.job?.id === m[1] && S.poll) return;
  stopPolling();
  openJob(m[1]);
}
function stopPolling() { clearTimeout(S.poll); clearInterval(S.tick); S.poll = S.tick = null; }

async function openJob(id) {
  showPane("progress");
  $("#create").scrollIntoView({ block: "start" });
  const res = await fetch(`/api/jobs/${id}`).catch(() => null);
  if (!res || !res.ok) { showPane("form"); showAlert(tr("err_not_found")); return; }
  handleJob(await res.json());
}

function handleJob(job) {
  S.job = job; S.lastPoll = Date.now();
  updateWork(job);
  if (job.status === "done") { stopPolling(); loadResult(job); return; }
  if (job.status === "error") {
    stopPolling(); showPane("form");
    showAlert(tr("err_" + (job.error || "failed")));
    $("#topic").value = job.topic;
    return;
  }
  showPane("progress");
  renderProgress(job);
  if (!S.tick) S.tick = setInterval(tickClock, 250);
  clearTimeout(S.poll);
  S.poll = setTimeout(async () => {
    const r = await fetch(`/api/jobs/${job.id}`).catch(() => null);
    if (r && r.ok) handleJob(await r.json()); else S.poll = setTimeout(() => handleJob(S.job), 2000);
  }, 1000);
}

function tickClock() {
  const j = S.job;
  if (!j) return;
  const dt = (Date.now() - S.lastPoll) / 1000;
  const left = j.status === "queued" ? j.remaining : Math.max(1, j.remaining - dt);
  $("#t-left").textContent = fmtClock(left);
  $("#t-el").textContent = fmtClock(j.status === "queued" ? 0 : j.elapsed + dt);
}

const STAGES = ["outline", "writing", "images", "design"];
function renderProgress(j) {
  const pct = Math.round(j.progress);
  $("#pct").textContent = `${pct}%`;
  $("#ring-bar").style.strokeDashoffset = String(326.7 * (1 - pct / 100));
  $("#stage-lbl").textContent = tr("lbl_" + j.status);
  $("#p-title").textContent = j.title || j.topic;
  $("#p-sub").textContent = tr("p_sub", { pages: j.pages, lang: LANG_NAMES[j.lang], eta: fmtHuman(j.estimate) });
  $("#queue-note").textContent = j.queue_pos ? tr("queue", { n: j.queue_pos }) : "";
  const si = STAGES.indexOf(j.status);
  $$("#stages li").forEach((li, i) => { li.className = i < si ? "done" : i === si ? "now" : ""; li.querySelector("i").textContent = i < si ? "✓" : String(i + 1); });
  const pal = j.palette;
  const dp = $("#design-pick");
  if (pal && pal.bg) {
    dp.classList.add("on");
    $("#pick-dots").innerHTML = [pal.bg[0], pal.bg[1], pal.accent, pal.accent2].map((c) => `<i style="background:#${c}"></i>`).join("");
    $("#pick-text").textContent = j.theme === "auto" ? tr("picked", { font: j.font_used }) : tr("picked_preset", { theme: themeName(j.theme), font: j.font_used });
  } else dp.classList.remove("on");
  const done = j.status === "writing" ? j.slides_done : si > 1 ? j.titles.length : 0;
  $("#titles").innerHTML = (j.titles || []).map((title, i) => {
    const cls = i < done ? "done" : j.status === "writing" ? "wip" : "";
    return `<li class="${cls}" style="animation-delay:${Math.min(i, 12) * 30}ms"><span class="n">${String(i + 2).padStart(2, "0")}</span><span>${esc(title)}</span><span class="s">${i < done ? "✓" : ""}</span></li>`;
  }).join("");
  tickClock();
}

/* ───────────────────────── result ───────────────────────── */
async function loadResult(job) {
  const r = await fetch(`/api/jobs/${job.id}/deck`).catch(() => null);
  if (!r || !r.ok) { showPane("form"); showAlert(tr("err_not_found")); return; }
  const data = await r.json();
  S.result = { job, ...data, imgs: new Set(data.images) };
  S.rTheme = data.theme; S.rFont = data.font; S.cur = 0;
  showPane("result");
  renderResultHead();
  renderSideControls();
  renderViewer();
}
function resultCtx(res = S.result) {
  const theme = S.rTheme === "auto" ? res.auto_theme : S.meta.themes[S.rTheme];
  const fontName = S.rFont === "auto" ? res.auto_font : S.rFont;
  return {
    deck: res.deck, theme, author: res.author, fontName,
    fontCss: S.meta.fonts[fontName] || "Arial, sans-serif",
    img: (name) => (res.imgs.has(name) ? `/api/jobs/${res.job.id}/img/${name}` : ""),
  };
}
function renderResultHead() {
  const { job, deck } = S.result;
  $("#r-title").textContent = deck.title;
  $("#r-meta").innerHTML = tr("r_meta", { n: deck.slides.length + 2, time: esc(fmtHuman(job.elapsed)) });
}
function renderSideControls() {
  $("#r-themes").innerHTML = ["auto", ...Object.keys(S.meta.themes)].map((k) => themeButton(k, S.rTheme === k)).join("");
  $("#r-font").innerHTML = [`<option value="auto">✨ ${tr("auto")} (${esc(S.result.auto_font)})</option>`,
    ...Object.keys(S.meta.fonts).map((f) => `<option value="${esc(f)}" ${S.rFont === f ? "selected" : ""}>${esc(f)}</option>`)].join("");
  $("#r-font").value = S.rFont;
  updateDownload();
}
function updateDownload() {
  const id = S.result.job.id;
  $("#dl").href = `/api/jobs/${id}/download?theme=${encodeURIComponent(S.rTheme)}&font=${encodeURIComponent(S.rFont)}`;
}
function renderViewer() {
  const ctx = resultCtx();
  const n = ctx.deck.slides.length + 2;
  S.cur = Math.max(0, Math.min(n - 1, S.cur));
  $("#stage").innerHTML = slideHtml(ctx, S.cur - 1);
  $("#counter").textContent = `${S.cur + 1} / ${n}`;
  const thumbs = $("#thumbs");
  if (thumbs.dataset.key !== `${S.result.job.id}|${S.rTheme}|${S.rFont}`) {
    thumbs.dataset.key = `${S.result.job.id}|${S.rTheme}|${S.rFont}`;
    thumbs.innerHTML = Array.from({ length: n }, (_, i) => `<button data-i="${i}">${slideHtml(ctx, i - 1)}</button>`).join("");
    requestAnimationFrame(() => fitAll(thumbs));
  }
  $$("#thumbs button").forEach((b) => b.classList.toggle("on", +b.dataset.i === S.cur));
  const active = $(`#thumbs button[data-i="${S.cur}"]`);
  active?.scrollIntoView({ block: "nearest", inline: "nearest" });
  const s = ctx.deck.slides[S.cur - 1];
  $("#notes-box").hidden = !(s && s.notes);
  $("#notes-text").textContent = s?.notes || "";
  requestAnimationFrame(() => fitAll($("#stage")));
}
function bindResult() {
  $("#prev").addEventListener("click", () => { S.cur--; renderViewer(); });
  $("#next").addEventListener("click", () => { S.cur++; renderViewer(); });
  $("#thumbs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { S.cur = +b.dataset.i; renderViewer(); } });
  document.addEventListener("keydown", (e) => {
    if (!$("#pane-result").classList.contains("on") || /input|textarea|select/i.test(document.activeElement?.tagName || "")) return;
    if (e.key === "ArrowRight") { S.cur++; renderViewer(); }
    if (e.key === "ArrowLeft") { S.cur--; renderViewer(); }
  });
  $("#r-themes").addEventListener("click", (e) => {
    const b = e.target.closest("[data-v]"); if (!b) return;
    S.rTheme = b.dataset.v; renderSideControls(); renderViewer();
  });
  $("#r-font").addEventListener("change", (e) => { S.rFont = e.target.value; updateDownload(); renderViewer(); });
  $("#new-btn").addEventListener("click", () => { S.result = null; S.job = null; history.pushState(null, "", "#create"); showPane("form"); $("#topic").focus(); });
  $("#copy").addEventListener("click", async () => {
    const url = `${location.origin}/#/p/${S.result.job.id}`;
    try { await navigator.clipboard.writeText(url); toast(tr("copied")); } catch { prompt("", url); }
  });
  let sx = null;
  $("#stage").addEventListener("touchstart", (e) => { sx = e.touches[0].clientX; }, { passive: true });
  $("#stage").addEventListener("touchend", (e) => {
    if (sx === null) return;
    const dx = e.changedTouches[0].clientX - sx; sx = null;
    if (Math.abs(dx) > 40) { S.cur += dx < 0 ? 1 : -1; renderViewer(); }
  });
}

/* ───────────────────────── my works ───────────────────────── */
function addWork(job) {
  const list = store.get("zs_works", []).filter((w) => w.id !== job.id);
  list.unshift({ id: job.id, topic: job.topic, title: job.title || "", pages: job.pages, created: job.created, status: job.status });
  store.set("zs_works", list.slice(0, 30));
  renderWorks();
}
function updateWork(job) {
  const list = store.get("zs_works", []);
  const w = list.find((x) => x.id === job.id);
  if (!w) { addWork(job); return; }
  if (w.status !== job.status || (job.title && w.title !== job.title)) {
    w.status = job.status; w.title = job.title || w.title;
    store.set("zs_works", list); renderWorks();
  }
}
function renderWorks() {
  const list = store.get("zs_works", []);
  const el = $("#works-list");
  if (!list.length) { el.innerHTML = `<div class="empty" style="grid-column:1/-1">${esc(tr("works_empty"))}</div>`; return; }
  el.innerHTML = list.map((w) => {
    const date = new Date((w.created || 0) * 1000).toLocaleDateString(UI === "ru" ? "ru-RU" : "kk-KZ");
    const done = w.status === "done";
    return `<article class="work"><div class="cover" style="background-image:url('/api/jobs/${w.id}/img/cover'),linear-gradient(135deg,#1e1b4b,#0e7490)"><span>${w.pages} · ${w.status === "done" ? "✓" : w.status === "error" ? "⚠" : esc(tr("lbl_" + w.status))}</span></div>
      <div class="in"><h3>${esc(w.title || w.topic)}</h3><small>${esc(date)}</small>
      <div class="acts"><a class="btn ghost small" href="#/p/${w.id}">${esc(tr("open"))}</a>${done ? `<a class="btn ghost small" href="/api/jobs/${w.id}/download">⬇ PPTX</a>` : ""}</div></div></article>`;
  }).join("");
}

/* ───────────────────────── designs gallery ───────────────────────── */
function renderGallery() {
  const sample = (title) => ({
    title, subtitle: "", thanks: "",
    slides: [{ layout: "cards", title, lead: tr("sample_lead"), bullets: I18N[UI].sample_b }],
  });
  $("#auto-explain").innerHTML = I18N[UI].autoex.map((x) => `<div><div class="pal">${x.p.map((c) => `<i style="background:#${c}"></i>`).join("")}</div><b>✨ ${esc(x.t)}</b>${esc(x.d)}</div>`).join("");
  $("#gallery").innerHTML = Object.entries(S.meta.themes).map(([k, th]) => {
    const ctx = { deck: sample(tr("sample_title")), theme: th, author: "", fontCss: "Arial, sans-serif", img: () => "" };
    return `<figure>${slideHtml(ctx, 0)}<figcaption>${esc(th.name[UI] || th.name.kk)}<small>${th.dark ? "dark" : "light"}</small></figcaption></figure>`;
  }).join("");
  requestAnimationFrame(() => fitAll($("#gallery")));
}

/* ───────────────────────── boot ───────────────────────── */
async function boot() {
  $("#year").textContent = new Date().getFullYear();
  $$("[data-ui]").forEach((b) => b.addEventListener("click", () => { UI = b.dataset.ui; store.set("zs_ui", UI); applyI18n(); }));
  $("#burger").addEventListener("click", () => $("#nav").classList.toggle("open"));
  $$("#nav a").forEach((a) => a.addEventListener("click", () => $("#nav").classList.remove("open")));
  bindForm();
  bindResult();
  applyI18n();
  try {
    S.meta = await (await fetch("/api/meta")).json();
  } catch {
    showAlert(tr("err_network"));
    return;
  }
  if (!S.meta.pages.includes(S.form.pages)) S.form.pages = 10;
  if (S.form.theme !== "auto" && !S.meta.themes[S.form.theme]) S.form.theme = "auto";
  if (S.form.font !== "auto" && !S.meta.fonts[S.form.font]) S.form.font = "auto";
  renderChoices(); renderGallery(); updateEta();
  if (!S.meta.ready) showAlert(tr("err_not_configured"), true);
  else if (S.meta.ai && S.meta.ai.ok === false && ["auth", "quota"].includes(S.meta.ai.error)) showAlert(tr("err_" + S.meta.ai.error), true);
  window.addEventListener("hashchange", route);
  route();
  let rt;
  window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => { if (S.result) { $("#thumbs").dataset.key = ""; renderViewer(); } }, 200); });
}
boot();
