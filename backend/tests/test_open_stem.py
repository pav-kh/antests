from app.generation.openai_client import build_open_stem


def test_build_open_stem_has_all_blocks():
    stem = build_open_stem(
        topic_title="От бизнес-проблемы к требованиям",
        case="В финтех-компании растёт количество обращений.",
        task="Сформулируйте до 5 уточняющих вопросов.",
        focus="Не нужно проектировать архитектуру.",
        criteria_visible="понимание бизнес-потребности; качество вопросов.",
    )
    # Header lines
    assert "до 2500 знаков с пробелами" in stem
    assert "Тип: открытый кейс. От бизнес-проблемы к требованиям" in stem
    # Body blocks, each on its own labelled line
    assert "В финтех-компании растёт количество обращений." in stem
    assert "Задание: Сформулируйте до 5 уточняющих вопросов." in stem
    assert "Фокус ответа: Не нужно проектировать архитектуру." in stem
    assert "Критерии оценки: понимание бизнес-потребности; качество вопросов." in stem
    # Blocks appear in the correct order (a reordering bug must fail)
    positions = [stem.index(x) for x in (
        "до 2500 знаков", "Тип: открытый кейс", "В финтех-компании",
        "Задание:", "Фокус ответа:", "Критерии оценки:")]
    assert positions == sorted(positions)
    assert stem.count("\n\n") == 2  # exactly two blank-line separators
    assert "\n\n\n" not in stem     # no tripled newlines
