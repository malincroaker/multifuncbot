from pathlib import Path

from multifuncbot.core.models import Button, Context, Screen, home_button, scenario_exit_button
from multifuncbot.modules.guide.content import STEPS


class Guide:
    name = "guide"
    menu_names = ("Stepwise", "Stepwise")
    retain_state_on_exit = True

    def title(self, ctx: Context) -> str:
        return ctx.tr("Stepwise · Пошаговый помощник", "Stepwise · Guided onboarding")

    def start(self, ctx: Context) -> Screen:
        step = ctx.state(self.name).get("step")
        return Screen(
            ctx.tr(
                "Stepwise\n\nТри шага работы над проектом и PDF-чеклист. "
                "Прогресс сохраняется при смене сценария и перезапуске.",
                "Stepwise\n\nA three-step project guide and a PDF checklist. "
                "Your progress survives scenario switches and restarts.",
            ),
            [
                [
                    Button(
                        ctx.tr("Открыть гайд", "Open guide")
                        if step is None or step >= 3
                        else ctx.tr(
                            f"Открыть гайд · шаг {step + 1} из 3",
                            f"Open guide · step {step + 1} of 3",
                        ),
                        "guide:open",
                    )
                ],
                [Button(ctx.tr("Скачать PDF", "Download PDF"), "guide:pdf")],
                [Button(ctx.tr("Связь с администратором", "Contact admin"), "guide:contact")],
                scenario_exit_button(ctx),
            ],
            back="" if ctx.settings.default_module else "home",
            refresh="guide:menu",
        )

    def step(self, ctx: Context) -> Screen:
        index = ctx.state(self.name).get("step")
        if index is None:
            return self.start(ctx)
        if index >= len(STEPS[ctx.language]):
            return Screen(
                ctx.tr(
                    "Гайд пройден! Скачайте чеклист или начните заново.",
                    "Guide complete! Download the checklist or start again.",
                ),
                [
                    [Button(ctx.tr("Скачать PDF", "Download PDF"), "guide:pdf")],
                    [Button(ctx.tr("Пройти гайд ещё раз", "Read guide again"), "guide:new")],
                    home_button(ctx),
                ],
                back="guide:back",
            )
        return Screen(
            ctx.tr(f"Шаг {index + 1} из 3\n\n", f"Step {index + 1} of 3\n\n")
            + STEPS[ctx.language][index],
            [
                [
                    Button(ctx.tr("Назад", "Back"), "guide:back"),
                    Button(ctx.tr("Далее", "Next"), "guide:next"),
                ],
                [Button(ctx.tr("Скачать PDF", "Download PDF"), "guide:pdf")],
                home_button(ctx),
            ],
            back="guide:back",
        )

    def action(self, ctx: Context, action: str) -> Screen:
        if action == "menu":
            return self.start(ctx)
        if action == "open":
            if ctx.state(self.name).get("step") is None:
                ctx.save(self.name, {"step": 0})
            return self.step(ctx)
        if action == "new":
            ctx.save(self.name, {"step": 0})
        elif action in ("next", "back"):
            index = ctx.state(self.name).get("step")
            if index is not None:
                if action == "back" and index == 0:
                    return self.start(ctx)
                ctx.save(
                    self.name, {"step": min(3, max(0, index + (1 if action == "next" else -1)))}
                )
        elif action == "pdf":
            screen = (
                self.start(ctx)
                if ctx.state("screen").get("refresh") == "guide:menu"
                else self.step(ctx)
            )
            filename = "checklist_ru.pdf" if ctx.language == "ru" else "checklist.pdf"
            screen.document = Path(__file__).parent / "files" / filename
            return screen
        elif action == "contact":
            if ctx.settings.admin_contact_url:
                return Screen(
                    ctx.tr("Связаться с администратором:", "Contact the administrator:"),
                    [
                        [
                            Button(
                                ctx.tr("Открыть контакт", "Open contact"),
                                url=ctx.settings.admin_contact_url,
                            )
                        ],
                        home_button(ctx),
                    ],
                    back="guide:menu",
                    refresh="guide:contact",
                )
            return Screen(
                ctx.tr(
                    "Это демонстрация. Контакт администратора пока не настроен.",
                    "This is a demo. An administrator contact is not configured.",
                ),
                [home_button(ctx)],
                back="guide:menu",
                refresh="guide:contact",
            )
        return self.step(ctx)

    def text(self, ctx: Context, text: str) -> Screen:
        return self.step(ctx)


def create(db, settings):
    return Guide()
