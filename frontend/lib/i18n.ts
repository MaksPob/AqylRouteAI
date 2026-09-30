/** Словарь интерфейса: русский, казахский, английский. */

export type Lang = "ru" | "kk" | "en";
export const LANGS: { code: Lang; label: string }[] = [
  { code: "ru", label: "Рус" },
  { code: "kk", label: "Қаз" },
  { code: "en", label: "Eng" },
];

const DICT = {
  appName:      { ru: "AqylRoute", kk: "AqylRoute", en: "AqylRoute" },
  tagline:      { ru: "Маршрут помощи ребёнку — в одном месте", kk: "Балаға көмек бағыты — бір жерде", en: "One route through every agency" },

  login:        { ru: "Вход", kk: "Кіру", en: "Sign in" },
  loginField:   { ru: "Логин", kk: "Логин", en: "Login" },
  password:     { ru: "Пароль", kk: "Құпия сөз", en: "Password" },
  signIn:       { ru: "Войти", kk: "Кіру", en: "Sign in" },
  signOut:      { ru: "Выйти", kk: "Шығу", en: "Sign out" },
  demoAccounts: { ru: "Демонстрационные учётные записи", kk: "Демонстрациялық тіркелгілер", en: "Demo accounts" },
  parentRole:   { ru: "Родитель", kk: "Ата-ана", en: "Parent" },
  curatorRole:  { ru: "Куратор", kk: "Куратор", en: "Curator" },

  myPlan:       { ru: "Ваш план", kk: "Сіздің жоспарыңыз", en: "Your plan" },
  myCases:      { ru: "Мои обращения", kk: "Менің өтініштерім", en: "My cases" },
  newCase:      { ru: "Начать интервью", kk: "Сұхбатты бастау", en: "Start interview" },
  childName:    { ru: "Имя ребёнка (необязательно)", kk: "Баланың аты (міндетті емес)", en: "Child's name (optional)" },
  start:        { ru: "Начать", kk: "Бастау", en: "Start" },

  question:     { ru: "Вопрос", kk: "Сұрақ", en: "Question" },
  of:           { ru: "из", kk: "/", en: "of" },
  why:          { ru: "Зачем это нужно", kk: "Бұл не үшін қажет", en: "Why we ask" },
  dontKnow:     { ru: "Не знаю", kk: "Білмеймін", en: "I don't know" },
  next:         { ru: "Дальше", kk: "Әрі қарай", en: "Next" },
  back:         { ru: "Назад", kk: "Артқа", en: "Back" },
  buildPlan:    { ru: "Построить маршрут", kk: "Бағытты құру", en: "Build the route" },
  building:     { ru: "Собираем ваш маршрут…", kk: "Бағытыңызды құрастырудамыз…", en: "Building your route…" },
  interviewDone:{ ru: "Интервью завершено", kk: "Сұхбат аяқталды", en: "Interview complete" },
  selectAtLeast:{ ru: "Выберите хотя бы один вариант", kk: "Кемінде бір нұсқаны таңдаңыз", en: "Choose at least one option" },

  stTODO:       { ru: "Нужно сделать", kk: "Істеу керек", en: "To do" },
  stIN_PROGRESS:{ ru: "В процессе", kk: "Орындалуда", en: "In progress" },
  stWAITING:    { ru: "Ждём ответа", kk: "Жауап күтудеміз", en: "Waiting" },
  stDONE:       { ru: "Выполнено", kk: "Орындалды", en: "Done" },
  stOVERDUE:    { ru: "Просрочено", kk: "Мерзімі өтті", en: "Overdue" },
  stBLOCKED:    { ru: "Заблокировано", kk: "Бөгелген", en: "Blocked" },
  stCANCELLED:  { ru: "Отменено", kk: "Тоқтатылды", en: "Cancelled" },

  prHIGH:       { ru: "Высокий приоритет", kk: "Жоғары маңыздылық", en: "High priority" },
  prMEDIUM:     { ru: "Средний приоритет", kk: "Орташа маңыздылық", en: "Medium priority" },
  prLOW:        { ru: "Низкий приоритет", kk: "Төмен маңыздылық", en: "Low priority" },

  due:          { ru: "Срок", kk: "Мерзімі", en: "Due" },
  who:          { ru: "Кто делает", kk: "Кім жасайды", en: "Responsible" },
  needDocs:     { ru: "Что понадобится", kk: "Не қажет болады", en: "What you'll need" },
  whereToGo:    { ru: "Куда обращаться", kk: "Қайда жүгіну керек", en: "Where to go" },
  whyStep:      { ru: "Зачем этот шаг", kk: "Бұл қадам не үшін", en: "Why this step" },
  dependsOn:    { ru: "Сначала нужно выполнить", kk: "Алдымен орындау керек", en: "Complete first" },
  overdueBy:    { ru: "просрочено на", kk: "мерзімі өтті", en: "overdue by" },
  days:         { ru: "дн.", kk: "күн", en: "days" },
  markDone:     { ru: "Отметить выполненным", kk: "Орындалды деп белгілеу", en: "Mark as done" },
  markProgress: { ru: "Я начал этим заниматься", kk: "Мен бұны бастадым", en: "I've started this" },
  markWaiting:  { ru: "Жду ответа", kk: "Жауап күтудемін", en: "Waiting for reply" },
  haveDoc:      { ru: "есть", kk: "бар", en: "have it" },
  needDoc:      { ru: "нужно получить", kk: "алу керек", en: "need to get" },

  dashboard:    { ru: "Панель куратора", kk: "Куратор панелі", en: "Curator dashboard" },
  allCases:     { ru: "Все кейсы", kk: "Барлық кейстер", en: "All cases" },
  pendingReview:{ ru: "Ожидает проверки", kk: "Тексеруді күтуде", en: "Awaiting review" },
  activeCase:   { ru: "В работе", kk: "Жұмыста", en: "Active" },
  interviewing: { ru: "Идёт интервью", kk: "Сұхбат жүруде", en: "Interview in progress" },
  confirmPlan:  { ru: "Подтвердить план", kk: "Жоспарды бекіту", en: "Confirm plan" },
  confirmHint:  { ru: "После подтверждения план станет виден родителю", kk: "Бекіткеннен кейін жоспар ата-анаға көрінеді", en: "Once confirmed, the plan becomes visible to the parent" },
  editStep:     { ru: "Изменить", kk: "Өзгерту", en: "Edit" },
  removeStep:   { ru: "Убрать из плана", kk: "Жоспардан алып тастау", en: "Remove from plan" },
  save:         { ru: "Сохранить", kk: "Сақтау", en: "Save" },
  cancel:       { ru: "Отмена", kk: "Болдырмау", en: "Cancel" },
  verifyStatus: { ru: "Подтвердить статус", kk: "Мәртебені растау", en: "Verify status" },
  parentReported:{ ru: "Со слов родителя, не подтверждено", kk: "Ата-ананың сөзімен, расталмаған", en: "Reported by parent, unverified" },
  setBlocker:   { ru: "Отметить блокер", kk: "Бөгетті белгілеу", en: "Flag a blocker" },

  notifications:{ ru: "Уведомления", kk: "Хабарламалар", en: "Notifications" },
  noNotifications:{ ru: "Новых уведомлений нет", kk: "Жаңа хабарлама жоқ", en: "No new notifications" },
  escalation:   { ru: "Эскалация", kk: "Эскалация", en: "Escalation" },
  history:      { ru: "История кейса", kk: "Кейс тарихы", en: "Case history" },

  supportTitle: { ru: "Поддержка для вас", kk: "Сізге қолдау", en: "Support for you" },
  phq9Start:    { ru: "Пройти короткий опрос о самочувствии", kk: "Әл-ауқат туралы қысқа сауалнама", en: "Take a short wellbeing check" },
  phq9Result:   { ru: "Результат", kk: "Нәтиже", en: "Result" },
  phq9Submit:   { ru: "Показать результат", kk: "Нәтижені көрсету", en: "Show result" },
  outOf:        { ru: "из", kk: "/", en: "out of" },

  notDiagnosis: { ru: "AI не ставит диагноз и не назначает лечение. Все шаги берутся из официального справочника услуг.", kk: "AI диагноз қоймайды және ем тағайындамайды. Барлық қадамдар ресми қызметтер анықтамалығынан алынады.", en: "The AI does not diagnose or prescribe. Every step comes from the official service catalogue." },
  provisional:  { ru: "Сроки ориентировочные, их уточняет куратор.", kk: "Мерзімдер болжамды, оларды куратор нақтылайды.", en: "Deadlines are provisional and refined by the curator." },
  demoMode:     { ru: "Демонстрационный режим без ключа OpenAI", kk: "OpenAI кілтінсіз демонстрациялық режим", en: "Demo mode — no OpenAI key" },
  loading:      { ru: "Загрузка…", kk: "Жүктелуде…", en: "Loading…" },
  nothingYet:   { ru: "Пока ничего нет", kk: "Әзірге ештеңе жоқ", en: "Nothing here yet" },
  stepsTotal:   { ru: "шагов в плане", kk: "жоспардағы қадам", en: "steps in the plan" },
  skipToContent:{ ru: "Перейти к содержимому", kk: "Мазмұнға өту", en: "Skip to content" },
} as const;

export type Key = keyof typeof DICT;

export function t(key: Key, lang: Lang): string {
  return DICT[key][lang] ?? DICT[key].ru;
}

export const ROLE_NAMES: Record<string, Record<Lang, string>> = {
  PARENT: { ru: "Родитель", kk: "Ата-ана", en: "Parent" },
  CLINIC: { ru: "Поликлиника", kk: "Емхана", en: "Clinic" },
  PSYCHIATRIST: { ru: "Врач-психиатр", kk: "Психиатр дәрігер", en: "Psychiatrist" },
  VKK: { ru: "ВКК", kk: "ДКК", en: "Medical commission" },
  MSE: { ru: "МСЭ", kk: "МӘС", en: "Disability assessment" },
  PMPC: { ru: "ПМПК", kk: "ПМПК", en: "Educational commission" },
  EDUCATIONAL_ORGANIZATION: { ru: "Организация образования", kk: "Білім беру ұйымы", en: "School or kindergarten" },
  REHABILITATION_CENTER: { ru: "Реабилитационный центр", kk: "Оңалту орталығы", en: "Rehabilitation centre" },
  SOCIAL_SERVICE: { ru: "Соцзащита", kk: "Әлеуметтік қорғау", en: "Social services" },
  CURATOR: { ru: "Куратор", kk: "Куратор", en: "Curator" },
};

export const STAGE_NAMES: Record<string, Record<Lang, string>> = {
  DIAGNOSTIC: { ru: "Медицинские документы", kk: "Медициналық құжаттар", en: "Medical documentation" },
  SOCIAL_LEGAL: { ru: "Социально-правовой статус", kk: "Әлеуметтік-құқықтық мәртебе", en: "Social and legal status" },
  EDUCATIONAL: { ru: "Образование", kk: "Білім беру", en: "Education" },
  REHABILITATION: { ru: "Реабилитация", kk: "Оңалту", en: "Rehabilitation" },
  VOCATIONAL: { ru: "Профессия и взросление", kk: "Кәсіп және ержету", en: "Vocational and adulthood" },
};

export const BLOCKER_NAMES: Record<string, Record<Lang, string>> = {
  MISSING_DOCUMENT: { ru: "Не хватает документа", kk: "Құжат жетіспейді", en: "Missing document" },
  WAITING_FOR_ORGANIZATION: { ru: "Ждём организацию", kk: "Ұйымды күтудеміз", en: "Waiting for organisation" },
  NO_APPOINTMENT: { ru: "Нет записи на приём", kk: "Қабылдауға жазылу жоқ", en: "No appointment available" },
  PARENT_UNAVAILABLE: { ru: "Родитель недоступен", kk: "Ата-ана қолжетімсіз", en: "Parent unavailable" },
  SERVICE_UNAVAILABLE: { ru: "Услуга недоступна в регионе", kk: "Қызмет өңірде қолжетімсіз", en: "Service unavailable in region" },
  UNKNOWN: { ru: "Другая причина", kk: "Басқа себеп", en: "Other reason" },
};

export const REGION_NAMES: Record<string, Record<Lang, string>> = {
  ASTANA: { ru: "Астана", kk: "Астана", en: "Astana" },
  KARAGANDA: { ru: "Карагандинская область", kk: "Қарағанды облысы", en: "Karaganda region" },
  ALMATY: { ru: "Алматы", kk: "Алматы", en: "Almaty" },
};

export function localName(map: Record<string, Record<Lang, string>>, key: string, lang: Lang): string {
  return map[key]?.[lang] ?? key;
}

export function formatDate(iso: string, lang: Lang): string {
  const locale = lang === "kk" ? "kk-KZ" : lang === "en" ? "en-GB" : "ru-RU";
  return new Date(iso).toLocaleDateString(locale, { day: "numeric", month: "long", year: "numeric" });
}
