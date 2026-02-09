"""Interactive onboarding wizard for first-time setup."""
import logging
import yaml
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm, FloatPrompt
from rich.panel import Panel

logger = logging.getLogger("btcmonitor.onboarding")
console = Console()

USER_CONFIG_PATH = Path(__file__).parent / "user_config.yaml"

# ── experience presets ───────────────────────────────

PRESETS = {
    "beginner": {
        "plain_english": True,
        "couples_mode": True,
        "smart_alerts": {
            "enabled": True,
            "dca_reminders": True,
            "dip_alerts": False,
            "milestone_alerts": True,
            "weekly_summary": True,
            "streak_alerts": True,
        },
        "alerts": {"desktop_notifications": True},
    },
    "intermediate": {
        "plain_english": True,
        "couples_mode": False,
        "smart_alerts": {
            "enabled": True,
            "dca_reminders": True,
            "dip_alerts": True,
            "milestone_alerts": True,
            "weekly_summary": True,
            "streak_alerts": True,
        },
        "alerts": {"desktop_notifications": True},
    },
    "advanced": {
        "plain_english": False,
        "couples_mode": False,
        "smart_alerts": {
            "enabled": True,
            "dca_reminders": True,
            "dip_alerts": True,
            "milestone_alerts": True,
            "weekly_summary": True,
            "streak_alerts": True,
        },
        "alerts": {"desktop_notifications": True},
    },
}

RISK_TUNING = {
    "conservative": {"smart_alerts": {"dip_alerts": False}},
    "moderate": {"smart_alerts": {"dip_alerts": True}},
    "aggressive": {"smart_alerts": {"dip_alerts": True}},
}


class OnboardingWizard:
    """Step-by-step setup for new users."""

    def __init__(self, db, monitor, goal_tracker, portfolio_tracker, config):
        self.db = db
        self.monitor = monitor
        self.goal_tracker = goal_tracker
        self.portfolio_tracker = portfolio_tracker
        self.config = config
        self.answers = {}

    def run(self) -> dict:
        """Run the full wizard. Returns generated user config."""
        self._welcome()
        self._ask_experience()
        self._ask_budget()
        self._ask_goal()
        self._ask_risk()
        self._ask_notifications()
        self._ask_couples()

        user_config = self._build_config()
        self._save_config(user_config)
        self._create_goal()
        self._create_portfolio()
        self._first_fetch()
        self._next_steps()
        return user_config

    # ── prompts ──────────────────────────────────────

    def _welcome(self):
        console.print(Panel(
            "[bold #F7931A]Welcome to Bitcoin Cycle Monitor![/bold #F7931A]\n\n"
            "Let's set everything up in a few quick questions.\n"
            "You can always change these settings later.",
            title="Onboarding", border_style="#F7931A",
        ))

    def _ask_experience(self):
        choice = Prompt.ask(
            "\n[bold]What's your Bitcoin experience level?[/bold]\n"
            "  1. Beginner — new to Bitcoin/crypto\n"
            "  2. Intermediate — understand basics, some investing\n"
            "  3. Advanced — experienced with on-chain metrics & cycles\n\n"
            "Choose",
            choices=["1", "2", "3"], default="1",
        )
        self.answers["experience"] = ["beginner", "intermediate", "advanced"][int(choice) - 1]

    def _ask_budget(self):
        amount = FloatPrompt.ask(
            "\n[bold]How much do you want to DCA per month (USD)?[/bold]",
            default=200.0,
        )
        self.answers["monthly_dca"] = amount

    def _ask_goal(self):
        has_goal = Confirm.ask(
            "\n[bold]Do you have a Bitcoin accumulation target?[/bold]",
            default=True,
        )
        if has_goal:
            goal_type = Prompt.ask(
                "Target in BTC or USD?",
                choices=["btc", "usd"], default="btc",
            )
            if goal_type == "btc":
                self.answers["target_btc"] = FloatPrompt.ask("Target BTC", default=0.1)
            else:
                self.answers["target_usd"] = FloatPrompt.ask("Target USD value", default=10000.0)
            self.answers["goal_name"] = Prompt.ask("Name your goal", default="My Bitcoin Goal")
        else:
            monthly = self.answers.get("monthly_dca", 200)
            suggested = round((monthly * 36) / 100000, 4)
            console.print(f"\n[dim]Here are some targets to consider at ${monthly:.0f}/month:[/dim]")
            console.print(f"  • {suggested:.4f} BTC (~3 years of DCA at $100K)")
            console.print(f"  • 0.01 BTC (1 million sats)")
            console.print(f"  • 0.1 BTC (10 million sats)")
            self.answers["target_btc"] = FloatPrompt.ask(
                "Pick a target BTC amount", default=suggested,
            )
            self.answers["goal_name"] = "My Bitcoin Goal"

    def _ask_risk(self):
        choice = Prompt.ask(
            "\n[bold]Risk tolerance?[/bold]\n"
            "  1. Conservative — steady DCA, no extras\n"
            "  2. Moderate — DCA + dip buying alerts\n"
            "  3. Aggressive — DCA + dip alerts + extra buy signals\n\n"
            "Choose",
            choices=["1", "2", "3"], default="2",
        )
        self.answers["risk"] = ["conservative", "moderate", "aggressive"][int(choice) - 1]

    def _ask_notifications(self):
        choice = Prompt.ask(
            "\n[bold]How do you want to receive updates?[/bold]\n"
            "  1. Terminal only\n"
            "  2. Terminal + Desktop notifications\n"
            "  3. Terminal + Desktop + Telegram bot\n\n"
            "Choose",
            choices=["1", "2", "3"], default="2",
        )
        self.answers["notifications"] = int(choice)

    def _ask_couples(self):
        self.answers["couples_mode"] = Confirm.ask(
            "\n[bold]Investing with a partner? (enables couples mode)[/bold]",
            default=False,
        )

    # ── config generation ────────────────────────────

    def _build_config(self) -> dict:
        """Generate user config dict from answers."""
        import copy
        from config import _deep_merge

        exp = self.answers["experience"]
        risk = self.answers["risk"]

        cfg = copy.deepcopy(PRESETS[exp])
        cfg = _deep_merge(cfg, RISK_TUNING[risk])
        cfg["default_monthly_dca"] = self.answers["monthly_dca"]
        cfg["couples_mode"] = self.answers.get("couples_mode", False)

        notif = self.answers.get("notifications", 2)
        if notif == 1:
            cfg.setdefault("alerts", {})["desktop_notifications"] = False
        if notif >= 3:
            cfg["telegram"] = {
                "enabled": True,
                "bot_token": "",
                "chat_id": "",
                "weekly_digest": True,
                "action_alerts": True,
                "critical_alerts": True,
            }

        return cfg

    def _save_config(self, cfg: dict):
        with open(USER_CONFIG_PATH, "w") as f:
            yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
        console.print(f"\n[green]✓[/green] Config saved to {USER_CONFIG_PATH}")

    # ── side effects ─────────────────────────────────

    def _create_goal(self):
        target_btc = self.answers.get("target_btc")
        target_usd = self.answers.get("target_usd")
        if not target_btc and not target_usd:
            return
        name = self.answers.get("goal_name", "My Bitcoin Goal")
        monthly = self.answers["monthly_dca"]
        self.goal_tracker.create_goal(
            name, target_btc=target_btc, target_usd=target_usd, monthly_dca=monthly,
        )
        target = f"{target_btc} BTC" if target_btc else f"${target_usd:,.0f}"
        console.print(f"[green]✓[/green] Goal created: '{name}' — target {target}")

    def _create_portfolio(self):
        monthly = self.answers["monthly_dca"]
        weekly = round(monthly / 4, 2)
        self.portfolio_tracker.create_portfolio("Main DCA", frequency="weekly", amount=weekly)
        console.print(f"[green]✓[/green] Portfolio created: 'Main DCA' — ${weekly:.0f}/week")

    def _first_fetch(self):
        console.print("\n[dim]Fetching current Bitcoin data...[/dim]")
        try:
            snapshot = self.monitor.fetch_and_store()
            price = snapshot.price.price_usd
            change = snapshot.price.change_24h_pct
            console.print(f"[bold #F7931A]BTC ${price:,.0f}[/bold #F7931A] ({change:+.1f}%)")
        except Exception as e:
            console.print(f"[yellow]Fetch failed: {e} — retry with 'python main.py setup'[/yellow]")

    def _next_steps(self):
        cmds = [
            ("python main.py action", "What should I do?"),
            ("python main.py simple", "Plain English summary"),
            ("python main.py charts", "Generate visual charts"),
            ("python main.py dashboard", "Full terminal dashboard"),
            ("python main.py goal status", "Check goal progress"),
        ]
        lines = "\n".join(f"  [bold]{cmd}[/bold]  — {desc}" for cmd, desc in cmds)

        tg_note = ""
        if self.answers.get("notifications", 0) >= 3:
            tg_note = "\n\n  [bold]python main.py telegram setup[/bold]  — Connect Telegram bot"

        console.print(Panel(
            f"[bold green]You're all set![/bold green]\n\n{lines}{tg_note}",
            title="Next Steps", border_style="green",
        ))
