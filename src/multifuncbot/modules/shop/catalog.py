"""Fictional physical products, prices in kopecks. No real inventory or sales."""

PRODUCTS = {
    "notebook": {
        "id": "notebook",
        "title": {"ru": "Блокнот «Точка»", "en": "Dot notebook"},
        "description": {
            "ru": "160 страниц для планов и внезапных идей. А5, бумага в точку.",
            "en": "160 pages for plans and sudden ideas. A5, dotted paper.",
        },
        "category": "paper",
        "price": 89000,
        "image": "notebook.svg",
        "color": "sage",
    },
    "planner": {
        "id": "planner",
        "title": {"ru": "Планер «Неделя»", "en": "Weekly planner"},
        "description": {
            "ru": "Недатированный планер. Один разворот — одна спокойная неделя.",
            "en": "An undated planner. One spread for a calmer week.",
        },
        "category": "paper",
        "price": 129000,
        "image": "planner.svg",
        "color": "sand",
    },
    "pencils": {
        "id": "pencils",
        "title": {"ru": "Карандаши, 6 штук", "en": "Pencil set, six"},
        "description": {
            "ru": "Шесть графитовых карандашей HB в картонном пенале.",
            "en": "Six HB graphite pencils in a simple paper sleeve.",
        },
        "category": "tools",
        "price": 39000,
        "image": "pencils.svg",
        "color": "peach",
    },
    "mug": {
        "id": "mug",
        "title": {"ru": "Кружка «Пауза»", "en": "Pause mug"},
        "description": {
            "ru": "Керамическая кружка, 300 мл. Для перерывов между хорошими идеями.",
            "en": "A 300 ml ceramic mug. For breaks between good ideas.",
        },
        "category": "everyday",
        "price": 119000,
        "image": "mug.svg",
        "color": "clay",
    },
    "tote": {
        "id": "tote",
        "title": {"ru": "Шоппер «С собой»", "en": "Everyday tote"},
        "description": {
            "ru": "Плотный хлопок, длинные ручки. Вмещает ноутбук и немного планов.",
            "en": "Heavy cotton, long handles. Room for a laptop and a few plans.",
        },
        "category": "everyday",
        "price": 149000,
        "image": "tote.svg",
        "color": "sage",
    },
    "clips": {
        "id": "clips",
        "title": {"ru": "Зажимы для заметок", "en": "Notes binder clips"},
        "description": {
            "ru": "Набор из четырёх металлических зажимов для небольшого порядка.",
            "en": "Four metal binder clips to keep small things together.",
        },
        "category": "tools",
        "price": 29000,
        "image": "clips.svg",
        "color": "sand",
    },
}
