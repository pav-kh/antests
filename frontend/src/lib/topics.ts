// Russian display titles for the 10 fixed topic keys (must match backend
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
};

export function topicTitle(topicId: string): string {
  return TOPIC_TITLES[topicId] ?? topicId;
}
