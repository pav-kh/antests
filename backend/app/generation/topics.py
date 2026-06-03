from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    subtopics: list[str]
    proportions: dict[str, float]  # {"base": 0.x, "specialist": 0.y}


TOPICS: list[Topic] = [
    Topic("fundamentals", "Фундаментальные компетенции",
          ["Информационные системы и виды ПО", "ООП", "Системное мышление"],
          {"base": 0.10, "specialist": 0.08}),
    Topic("methodology", "Методологии и технологии разработки ПО",
          ["SDLC", "Waterfall/RUP/Scrum/Kanban/Lean/FDD/XP", "RACI", "CI/CD", "Проектная документация"],
          {"base": 0.10, "specialist": 0.10}),
    Topic("requirements", "Работа с требованиями",
          ["Виды требований", "Сбор и выявление", "Документирование", "ЖЦ и управление требованиями", "Критерии качества"],
          {"base": 0.15, "specialist": 0.14}),
    Topic("modeling", "Моделирование процессов и систем",
          ["UML (классы, use case, состояния, активности, последовательности)", "BPMN", "Иерархия моделей"],
          {"base": 0.15, "specialist": 0.14}),
    Topic("architecture", "Основные архитектурные практики",
          ["Стили архитектуры", "Клиент-сервер", "Монолит/распределённые", "Репликация/кластеры/бэкапы", "DDD/Event-Driven", "4+1/TOGAF"],
          {"base": 0.10, "specialist": 0.14}),
    Topic("data", "Хранение и обработка данных",
          ["Типы БД и СУБД", "Уровни моделирования", "ER-диаграммы", "SQL", "DDL", "ETL/витрины"],
          {"base": 0.12, "specialist": 0.12}),
    Topic("integration", "Интеграционные решения",
          ["TCP/IP/HTTP/HTTPS", "REST/OpenAPI", "SOAP/XSD", "Async (RabbitMQ/Kafka/AsyncAPI)", "DFD", "Виртуализация/контейнеры"],
          {"base": 0.10, "specialist": 0.12}),
    Topic("ux", "Проектирование пользовательских интерфейсов",
          ["Эргономика и эвристики", "Прототипы (low/high fidelity)", "CJM/карты эмпатии/A-B", "Роль СА в UI"],
          {"base": 0.06, "specialist": 0.06}),
    Topic("security", "Информационная безопасность",
          ["Аутентификация/идентификация", "OAuth/JWT/OpenID/cookies/API-key", "Авторизация и ролевая модель", "ЭЦП", "Уязвимости/мониторинг"],
          {"base": 0.06, "specialist": 0.06}),
    Topic("deployment", "Внедрение и сопровождение ПО",
          ["Виды тестирования", "Критерии качества ПО", "Управление дефектами", "ITIL/инциденты", "Релизы/пилотирование/обучение"],
          {"base": 0.06, "specialist": 0.04}),
]

_BY_ID = {t.id: t for t in TOPICS}


def get_topic(topic_id: str) -> Topic:
    return _BY_ID[topic_id]
