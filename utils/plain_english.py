"""Plain English translation layer for Bitcoin metrics.

Converts technical metrics into simple, jargon-free explanations
suitable for people who are new to Bitcoin and crypto.
"""
from models.enums import SignalStatus


def explain_fear_greed(value):
    """Translate Fear & Greed index into plain English."""
    if value is None:
        return "Market mood data is unavailable right now."

    value = int(value)
    if value <= 10:
        return (f"Market mood: {value}/100 -- Extreme Fear. "
                "Almost everyone is panicking and selling. Historically, "
                "these moments have been some of the best times to buy. "
                "Think of it like a massive clearance sale.")
    elif value <= 25:
        return (f"Market mood: {value}/100 -- Fear. "
                "Most people are nervous. Prices tend to be discounted "
                "when fear is this high. Warren Buffett's advice applies: "
                "be greedy when others are fearful.")
    elif value <= 45:
        return (f"Market mood: {value}/100 -- Somewhat Fearful. "
                "People are cautious but not panicking. This is a pretty "
                "normal environment for steady DCA buying.")
    elif value <= 55:
        return (f"Market mood: {value}/100 -- Neutral. "
                "The market isn't particularly scared or excited. "
                "A calm, unremarkable moment -- just keep your plan going.")
    elif value <= 75:
        return (f"Market mood: {value}/100 -- Greed. "
                "People are getting excited and optimistic. Prices may be "
                "running hot. Not a time to chase -- stick to your DCA amount.")
    else:
        return (f"Market mood: {value}/100 -- Extreme Greed. "
                "Everyone is euphoric and buying aggressively. Historically, "
                "this is when the market is most likely to reverse. "
                "Definitely not the time to go all-in.")


def explain_mvrv(value):
    """Translate MVRV ratio into plain English."""
    if value is None:
        return "MVRV data is unavailable. This metric compares what Bitcoin is worth now vs. what people paid for it."

    if value < 0.8:
        zone = "deep bargain territory"
        action = "This has historically been an excellent time to accumulate."
    elif value < 1.0:
        zone = "undervalued"
        action = "Bitcoin is trading below what the average holder paid. This is historically cheap."
    elif value < 1.5:
        zone = "near fair value"
        action = "Prices are reasonable -- not a screaming deal, but not overheated either."
    elif value < 2.5:
        zone = "above fair value"
        action = "The market is warming up. DCA is still fine, but don't overextend."
    elif value < 3.5:
        zone = "getting overheated"
        action = "Historically, this zone precedes corrections. Be cautious about adding large amounts."
    else:
        zone = "historically overheated"
        action = "Past cycles have peaked around these levels. Consider taking some profits or pausing DCA."

    return (f"MVRV is {value:.2f} -- {zone}. "
            f"This compares Bitcoin's current price to what people actually paid for their coins. "
            f"{action}")


def explain_drawdown(pct, ath=None):
    """Translate drawdown percentage into plain English."""
    if pct is None:
        return "Drawdown data is unavailable."

    ath_str = f" (~${ath:,.0f})" if ath else ""

    if pct < 5:
        return (f"Bitcoin is only {pct:.0f}% below its all-time high{ath_str}. "
                "We're near the top -- exciting but risky territory.")
    elif pct < 20:
        return (f"Bitcoin is {pct:.0f}% below its all-time high{ath_str}. "
                "A normal pullback. These happen regularly even in bull markets.")
    elif pct < 40:
        return (f"Bitcoin is {pct:.0f}% below its all-time high{ath_str}. "
                "A significant correction, but not unusual in Bitcoin's history. "
                "Past cycles have seen similar dips before resuming upward.")
    elif pct < 60:
        return (f"Bitcoin is {pct:.0f}% below its all-time high{ath_str}. "
                "A deep correction. In past cycles, drops of 40-60% have been "
                "where patient, long-term buyers accumulated the most Bitcoin.")
    else:
        return (f"Bitcoin is {pct:.0f}% below its all-time high{ath_str}. "
                "A severe downturn. While painful, every previous crash of this "
                "magnitude has eventually recovered to new highs. This is where "
                "disciplined DCA pays off the most.")


def explain_hash_rate(difficulty_change_pct):
    """Translate network HR / mining health into plain English."""
    if difficulty_change_pct is None:
        return "Mining data is unavailable."

    if difficulty_change_pct > 10:
        return (f"Mining power is surging (difficulty up {difficulty_change_pct:.1f}%). "
                "Miners are investing heavily in new equipment -- they believe "
                "Bitcoin's future is bright. Strong network = healthy Bitcoin.")
    elif difficulty_change_pct > 0:
        return (f"Mining power is growing steadily (difficulty up {difficulty_change_pct:.1f}%). "
                "The network is healthy and miners are profitable. This is normal "
                "and positive.")
    elif difficulty_change_pct > -10:
        return (f"Mining power dipped slightly (difficulty {difficulty_change_pct:.1f}%). "
                "Some miners may be under pressure, but nothing alarming. "
                "Small fluctuations are normal.")
    else:
        return (f"Mining power is declining significantly (difficulty {difficulty_change_pct:.1f}%). "
                "Miners are struggling -- possibly shutting down equipment because "
                "prices are too low to be profitable. This is a stress signal, but "
                "it also means the worst of the selling pressure may be near its end.")


def explain_cycle_phase(phase_name, days_since_halving, cycle_pct):
    """Translate cycle position into plain English."""
    years = days_since_halving / 365

    season_map = {
        "ACCUMULATION": ("early spring", "The quiet before the next growth phase. Smart money is loading up."),
        "EARLY_BULL": ("spring", "Things are starting to warm up. Early signs of a new bull market."),
        "MID_BULL": ("summer", "Full bull market mode. Prices are climbing and optimism is high."),
        "LATE_BULL": ("late summer", "The party is raging, but it won't last forever. Be cautious."),
        "DISTRIBUTION": ("early fall", "Big holders may be selling to newcomers. Watch for signs of a top."),
        "EARLY_BEAR": ("fall", "The tide is turning. Prices are pulling back from highs."),
        "MID_BEAR": ("winter", "Full bear market. Prices are down, fear is up. This is when fortunes are built quietly."),
        "CAPITULATION": ("deep winter", "Maximum pain. Everyone has given up. But dawn always follows the darkest night."),
    }

    season, desc = season_map.get(phase_name, ("unknown", ""))

    return (f"We're {days_since_halving} days into the current 4-year cycle ({cycle_pct:.0f}% through). "
            f"Think of it like {season} in Bitcoin's seasons. {desc} "
            f"Bitcoin halves its new supply roughly every 4 years, creating a predictable rhythm "
            f"of boom and bust that has repeated since 2012.")


def explain_dominance(pct):
    """Translate BTC dominance into plain English."""
    if pct is None:
        return "Dominance data unavailable."
    if pct > 60:
        return (f"Bitcoin dominance is {pct:.1f}% -- investors are sticking with Bitcoin "
                "over altcoins. This is typical in uncertain or early bull markets.")
    elif pct > 45:
        return (f"Bitcoin dominance is {pct:.1f}% -- a healthy mix between Bitcoin "
                "and other cryptocurrencies. Nothing unusual.")
    else:
        return (f"Bitcoin dominance is {pct:.1f}% -- money is flowing into altcoins. "
                "This often happens in the late stages of a bull market.")


def get_traffic_light(snapshot, nadeau_signals):
    """Return a traffic light signal: GREEN, YELLOW, or RED with action item.

    Args:
        snapshot: CombinedSnapshot with current metrics
        nadeau_signals: dict from CycleAnalyzer.get_nadeau_signals() or
                       NadeauSignalEvaluator.get_full_assessment()
    """
    # Count signals
    if "signals" in nadeau_signals:
        # From CycleAnalyzer.get_nadeau_signals()
        signals = nadeau_signals["signals"]
        bullish = sum(1 for _, s, _, _ in signals if s == SignalStatus.BULLISH)
        bearish = sum(1 for _, s, _, _ in signals if s == SignalStatus.BEARISH)
    else:
        # From NadeauSignalEvaluator.get_full_assessment()
        overall = nadeau_signals.get("overall_bias", SignalStatus.NEUTRAL)
        bullish = 2 if overall == SignalStatus.BULLISH else (1 if overall == SignalStatus.NEUTRAL else 0)
        bearish = 2 if overall == SignalStatus.BEARISH else (1 if overall == SignalStatus.NEUTRAL else 0)

    fear = snapshot.sentiment.fear_greed_value if snapshot else 50
    mvrv = snapshot.valuation.mvrv_ratio if snapshot else None

    # Decision logic
    if bullish > bearish and fear < 40:
        color = "GREEN"
        label = "Favorable for Accumulation"
        action = "Keep DCA'ing -- conditions are historically favorable for buying."
    elif bearish > bullish + 1 or (mvrv is not None and mvrv > 3.0) or fear > 75:
        color = "RED"
        label = "Caution -- Overheated"
        action = "Consider pausing or reducing your DCA. The market looks overheated."
    else:
        color = "YELLOW"
        label = "Mixed Signals"
        action = "Stay the course with your regular DCA. No strong signal either way."

    return {
        "color": color,
        "label": label,
        "action": action,
    }


def explain_overall_signal(snapshot, nadeau_signals, cycle_info=None, monthly_dca=200):
    """Generate a complete plain English summary with traffic light and action items."""
    light = get_traffic_light(snapshot, nadeau_signals)
    parts = []

    # Traffic light header
    color_rich = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}[light["color"]]
    parts.append(f"[bold {color_rich}]Signal: {light['color']} -- {light['label']}[/bold {color_rich}]")
    parts.append(f"{light['action']}\n")

    # Key metrics in plain English
    if snapshot:
        parts.append(explain_fear_greed(snapshot.sentiment.fear_greed_value))
        parts.append("")
        parts.append(explain_mvrv(snapshot.valuation.mvrv_ratio))
        parts.append("")

        # Drawdown
        if "signals" in nadeau_signals:
            for name, status, value, interp in nadeau_signals["signals"]:
                if name == "Drawdown":
                    parts.append(explain_drawdown(value))
                    break

        parts.append("")
        parts.append(explain_hash_rate(snapshot.onchain.difficulty_change_pct))
        parts.append("")
        parts.append(explain_dominance(snapshot.sentiment.btc_dominance_pct))

    # Cycle context
    if cycle_info:
        parts.append("")
        phase = cycle_info.get("phase", {})
        phase_name = phase.get("phase", "UNKNOWN")
        if hasattr(phase_name, "name"):
            phase_name = phase_name.name
        halving = cycle_info.get("halving", {})
        days = halving.get("days_since", 0)
        pct = halving.get("cycle_pct_elapsed", 0)
        parts.append(explain_cycle_phase(phase_name, days, pct))

    # DCA context
    if snapshot and monthly_dca > 0:
        price = snapshot.price.price_usd
        sats = int((monthly_dca / price) * 100_000_000) if price > 0 else 0
        parts.append(f"\nWhat this means for your ${monthly_dca}/month DCA: "
                    f"At today's price of ${price:,.0f}, you'd get roughly "
                    f"{sats:,} sats ({monthly_dca / price:.6f} BTC) per buy.")

    return "\n".join(parts)


def get_couple_framing(summary_text):
    """Add couple-friendly framing to the summary."""
    header = (
        "[bold]Here's what you both should know this week:[/bold]\n"
        "This is your shared Bitcoin update -- no jargon, just the facts "
        "you need to make decisions together.\n"
    )
    footer = (
        "\n[dim]Remember: You're in this together. Stick to your plan, "
        "talk through any changes, and trust the process.[/dim]"
    )
    return header + summary_text + footer


# Educational content for the 'learn' command
EDUCATIONAL_TOPICS = [
    {
        "title": "What is Bitcoin's Halving?",
        "content": (
            "Every ~4 years, the amount of new Bitcoin created per block gets cut in half. "
            "This is called the 'halving.' It makes Bitcoin scarcer over time.\n\n"
            "After each halving, there's historically been a bull market within 12-18 months, "
            "followed by a correction. We're currently in the 4th cycle (halving was April 2024).\n\n"
            "Next halving: ~April 2028. By then, the reward drops from 3.125 to 1.5625 BTC per block."
        ),
    },
    {
        "title": "What is DCA (Dollar Cost Averaging)?",
        "content": (
            "DCA means investing a fixed dollar amount on a regular schedule, "
            "regardless of the price. For example, $200 every Monday.\n\n"
            "When prices are high, you buy less Bitcoin. When prices are low, you buy more. "
            "Over time, this averages out your cost and removes the stress of trying to "
            "'time the market.'\n\n"
            "Studies show DCA outperforms lump-sum investing in volatile, declining markets "
            "-- exactly the kind of market Bitcoin often is."
        ),
    },
    {
        "title": "What is MVRV?",
        "content": (
            "MVRV stands for Market Value to Realized Value. It compares what Bitcoin "
            "is worth NOW (market price x all coins) vs. what everyone actually PAID "
            "for their coins.\n\n"
            "- Below 1.0: Bitcoin is cheaper than what people paid -- historically a bargain\n"
            "- 1.0 to 2.0: Fair value range\n"
            "- Above 3.0: Historically overheated -- past cycle tops were around 3.5-4.0\n\n"
            "Think of it like a house: if it's selling for less than what people paid to build it, "
            "it's probably undervalued."
        ),
    },
    {
        "title": "What is Fear & Greed Index?",
        "content": (
            "The Fear & Greed Index measures market sentiment on a scale of 0-100.\n\n"
            "- 0-25: Extreme Fear (everyone is panicking)\n"
            "- 25-45: Fear (people are nervous)\n"
            "- 45-55: Neutral\n"
            "- 55-75: Greed (people are optimistic)\n"
            "- 75-100: Extreme Greed (euphoria)\n\n"
            "The contrarian strategy: buy when others are fearful, be cautious when "
            "others are greedy. Extreme fear has historically been a better buying "
            "opportunity than extreme greed."
        ),
    },
    {
        "title": "Why Does Network HR Matter?",
        "content": (
            "Network HR (hashrate) is the total computing power securing the Bitcoin network. "
            "When it goes up, it means miners are investing in more equipment -- "
            "they believe Bitcoin will be valuable enough to cover their costs.\n\n"
            "When network HR drops significantly, miners may be shutting down because "
            "they're losing money. This can signal a market bottom is near, because "
            "mining becomes unprofitable before prices recover.\n\n"
            "Rising network HR = healthy network, confident miners."
        ),
    },
    {
        "title": "Bitcoin's 4-Year Cycle",
        "content": (
            "Bitcoin has followed a roughly 4-year pattern since its creation:\n\n"
            "Year 1 (post-halving): Supply shock kicks in. Often starts a bull run.\n"
            "Year 2: Peak territory. The market gets euphoric, then corrects.\n"
            "Year 3: Bear market / correction. Fear dominates, prices drop.\n"
            "Year 4: Recovery and accumulation. Smart money loads up before the next halving.\n\n"
            "Past performance doesn't guarantee future results, but this pattern has "
            "repeated for 3 full cycles so far. We're in cycle 4."
        ),
    },
    {
        "title": "What Does 'Sats' Mean?",
        "content": (
            "A 'sat' (short for satoshi) is the smallest unit of Bitcoin. "
            "1 Bitcoin = 100,000,000 sats.\n\n"
            "When Bitcoin costs $70,000, your $200 DCA buys about 285,714 sats. "
            "Many Bitcoiners think in sats rather than whole Bitcoin, since most people "
            "can't afford a whole coin.\n\n"
            "Stacking sats = accumulating small amounts of Bitcoin over time. "
            "That's exactly what DCA does."
        ),
    },
    {
        "title": "Why We Don't Try to Time the Market",
        "content": (
            "Timing the market means trying to buy at the bottom and sell at the top. "
            "Sounds great, but almost nobody can do it consistently.\n\n"
            "Missing just the 10 best days in Bitcoin's history would have dramatically "
            "reduced your returns. And those best days often come right after the worst days "
            "-- when everyone is too scared to buy.\n\n"
            "DCA solves this: you buy on schedule, accumulate more when prices are low, "
            "and don't have to stress about picking the perfect moment."
        ),
    },
]
