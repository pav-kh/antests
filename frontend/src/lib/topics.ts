// Russian display titles for the 18 topic keys (must match backend
// app/generation/topics.py). Used everywhere a topic_id is shown to the user.
export const TOPIC_TITLES: Record<string, string> = {
  fundamentals: "Фундаментальные компетенции",
  methodology: "Методологии и технологии разработки ПО",
  requirements: "Работа с требованиями",
  modeling: "Моделирование процессов и систем",
  architecture: "Основные архитектурные практики",
  data: "Хранение и обработка данных",
  integration: "Интеграционные решения",
  ux: "Проектирование пользовательских интерфейсов",
  security: "Информационная безопасность",
  deployment: "Внедрение и сопровождение ПО",
  // BA-level (ba) topics
  stakeholders: "Анализ и управление стейкхолдерами",
  strategy: "Стратегический анализ и бизнес-обоснование",
  process_analysis: "Анализ и улучшение бизнес-процессов",
  elicitation: "Выявление требований: техники",
  solution_value: "Оценка и приёмка решения",
  agile_ba: "Бизнес-анализ в Agile",
  ba_planning: "Планирование и мониторинг БА-работ",
  soft_skills: "Коммуникации и софт-скиллы аналитика",
};

export function topicTitle(topicId: string): string {
  return TOPIC_TITLES[topicId] ?? topicId;
}
