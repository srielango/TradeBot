"""Market Sentiment Analyzer module evaluating RSS news feeds for macro catalysts.

Identifies major sentiment drivers and drastic market condition changers such as:
- Outbreak of war or geopolitical conflicts
- Favourable or unfavourable union budget announcements
- Major regulatory and economic policy changes (RBI, SEBI, Government)
- Systemic market shocks, crashes, or all-time high rallies
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import html
import re
import xml.etree.ElementTree as ET

import requests

# Standard financial RSS feeds for Indian & global market catalysts
DEFAULT_RSS_FEEDS: dict[str, str] = {
    "Economic Times Markets": (
        "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"
    ),
    "Livemint Markets": "https://www.livemint.com/rss/markets",
    "Moneycontrol Latest": "https://www.moneycontrol.com/rss/latestnews.xml",
    "Google News Business (India)": (
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-IN&gl=IN&ceid=IN:en"
    ),
}

# ── Catalyst Patterns (Keywords & Regular Expressions) ───────────────────────

# High-impact drastic catalyst categories
WAR_CONFLICT_KEYWORDS = [
    r"\bwar\b",
    r"\bconflict\b",
    r"\binvasion\b",
    r"\bmilitary\b",
    r"\bairstrike\b",
    r"\bmissile\b",
    r"\btroops\b",
    r"\bhostilities\b",
    r"\bceasefire\b",
    r"\bsanctions\b",
    r"\bgeopolitical\b",
    r"\bterror\b",
    r"\bescalat\w+",
    r"\bmiddle east conflict\b",
    r"\bcrude surge\b",
    r"\boil spike\b",
]

BUDGET_FISCAL_KEYWORDS = [
    r"\bunion budget\b",
    r"\bbudget 20\w*",
    r"\bfavourable budget\b",
    r"\bfavorable budget\b",
    r"\btax cut\b",
    r"\btax relief\b",
    r"\bcorporate tax\b",
    r"\bincome tax relief\b",
    r"\bcapital gains tax\b",
    r"\bstt\b",
    r"\bfiscal deficit\b",
    r"\bcapex boost\b",
    r"\bfiscal stimulus\b",
    r"\bgst cut\b",
    r"\bgst reduction\b",
    r"\bbudget cheer\b",
    r"\bbudget sops\b",
]

POLICY_REGULATORY_KEYWORDS = [
    r"\bmajor policy\b",
    r"\bpolicy change\b",
    r"\bcabinet approves\b",
    r"\brbi policy\b",
    r"\brepo rate\b",
    r"\brate hike\b",
    r"\brate cut\b",
    r"\bmonetary policy committee\b",
    r"\bmpc\b",
    r"\bsebi\b",
    r"\bsebi norm\w*",
    r"\bsebi regulation\w*",
    r"\bfdi\b",
    r"\bimport duty\b",
    r"\bexport duty\b",
    r"\btariff\b",
    r"\btrade ban\b",
    r"\bpli scheme\b",
    r"\bprivatization\b",
    r"\bdisinvestment\b",
    r"\border on\b",
    r"\bordinance\b",
    r"\breform\w*",
]

CRASH_SHOCK_KEYWORDS = [
    r"\bmarket crash\b",
    r"\bmeltdown\b",
    r"\bblack swan\b",
    r"\bbanking crisis\b",
    r"\bliquidity crunch\b",
    r"\bcontagion\b",
    r"\bdefault\b",
    r"\brupee plunge\b",
    r"\brecord low rupee\b",
    r"\binflation spike\b",
    r"\brecession\b",
    r"\bcircuit breaker\b",
    r"\bmassive selloff\b",
]

BULLISH_CATALYST_KEYWORDS = [
    r"\ball-time high\b",
    r"\brecord high\b",
    r"\bmassive rally\b",
    r"\bmarket surges\b",
    r"\bfpi inflow\b",
    r"\bgdp beat\w*",
    r"\bsovereign upgrade\b",
    r"\brating upgrade\b",
    r"\bblockbuster earnings\b",
    r"\bmega merger\b",
]

# ── Sentiment Polarity Lexicons ──────────────────────────────────────────────

BULLISH_WORDS = {
    "gain", "gains", "gaining", "gained", "surge", "surges", "surging", "surged",
    "jump", "jumps", "jumped", "rally", "rallies", "rallying", "soar", "soars",
    "soaring", "boost", "boosts", "boosted", "record", "profit", "profits",
    "profitable", "buy", "buying", "bullish", "upbeat", "rebound", "rebounds",
    "upgrade", "upgrades", "upgraded", "high", "higher", "highs", "expansion",
    "optimistic", "optimism", "favourable", "favorable", "growth", "growing",
    "relief", "stimulus", "dividend", "dividends", "green", "beat", "beats",
    "cheer", "cheers", "outperform", "outperformed", "advances", "advancing",
    "peace", "ceasefire", "diplomacy", "easing", "eased", "recovery", "recover",
}

BEARISH_WORDS = {
    "drop", "drops", "dropping", "dropped", "fall", "falls", "falling", "fell",
    "slump", "slumps", "slumping", "slide", "slides", "sliding", "plunge", "plunges",
    "plunging", "crash", "crashes", "crashing", "crashed", "loss", "losses",
    "sell", "selling", "selloff", "bearish", "down", "downgrade", "downgrades",
    "downgraded", "low", "lower", "lows", "contraction", "pessimistic", "risk",
    "risks", "threat", "threats", "concern", "concerns", "inflation", "war",
    "conflict", "strike", "strikes", "sanction", "sanctions", "hike", "hikes",
    "penalty", "penalties", "fraud", "default", "defaults", "deficit", "blow",
    "tumble", "tumbles", "underperform", "headwind", "headwinds", "tension",
    "tensions", "fear", "fears", "curb", "curbs", "ban", "bans", "cautious",
    "weak", "weakness", "plummets",
}


@dataclass
class MarketNewsItem:
    """Represents an individual news event parsed from an RSS feed with sentiment score."""

    title: str
    description: str
    link: str
    pub_date: str
    source: str
    sentiment: str  # "BULLISH", "BEARISH", "NEUTRAL"
    sentiment_score: float  # -1.0 (strongly bearish) to +1.0 (strongly bullish)
    impact_level: str  # "HIGH", "MEDIUM", "LOW"
    is_drastic: bool  # True if high impact macro change
    catalyst_category: str  # Category name e.g. "Geopolitical Risk / War"
    catalyst_reason: str  # Short description of why it was flagged


@dataclass
class MarketSentimentSummary:
    """Summary of overall market sentiment and detected high-impact macro catalysts."""

    overall_sentiment: str
    sentiment_score: float
    bullish_count: int
    bearish_count: int
    neutral_count: int
    drastic_events_count: int
    high_impact_items: list[MarketNewsItem] = field(default_factory=list)
    all_items: list[MarketNewsItem] = field(default_factory=list)
    timestamp: str = ""
    summary_headline: str = ""


class MarketSentimentAnalyzer:
    """Analyzer providing RSS feed ingestion, catalyst extraction, and sentiment scoring."""

    def __init__(self, feeds: dict[str, str] | None = None) -> None:
        """Initialize the analyzer with custom or default RSS feed sources.

        Args:
            feeds (dict[str, str] | None): Mapping of feed names to RSS XML URLs.
        """
        self.feeds = feeds or DEFAULT_RSS_FEEDS

    @staticmethod
    def _clean_html(raw_html: str) -> str:
        """Strip HTML markup and decode XML entities from RSS text content.

        Args:
            raw_html (str): Raw string containing potential HTML tags.

        Returns:
            str: Clean text representation.
        """
        if not raw_html:
            return ""
        clean_text = re.sub(r"<[^>]+>", " ", raw_html)
        clean_text = html.unescape(clean_text)
        return " ".join(clean_text.split())

    def _classify_catalyst(
        self, text: str
    ) -> tuple[bool, str, str, str]:
        """Detect whether the news text signifies a drastic market condition change.

        Args:
            text (str): Combined news title and description.

        Returns:
            tuple[bool, str, str, str]:
                - is_drastic (bool): True if drastic market mover.
                - impact_level (str): "HIGH", "MEDIUM", or "LOW".
                - category (str): Human-readable catalyst category.
                - reason (str): Explanatory rationale.
        """
        lower = text.lower()

        # Check 1: War & Geopolitical Conflict
        for pat in WAR_CONFLICT_KEYWORDS:
            if re.search(pat, lower):
                # Peace / Ceasefire nuance
                if "ceasefire" in lower or "diplomacy" in lower or "peace talks" in lower:
                    return (
                        True,
                        "HIGH",
                        "Geopolitical / Diplomacy",
                        "De-escalation or diplomacy detected regarding conflict",
                    )
                return (
                    True,
                    "HIGH",
                    "Geopolitical Risk / War",
                    "Geopolitical conflict, military action, or war tension detected",
                )

        # Check 2: Union Budget & Fiscal Policy
        for pat in BUDGET_FISCAL_KEYWORDS:
            if re.search(pat, lower):
                fav_cues = ["cut", "relief", "boost", "cheer", "sops", "incentive"]
                if any(w in lower for w in fav_cues):
                    return (
                        True,
                        "HIGH",
                        "Fiscal / Budget (Favourable)",
                        "Favourable union budget announcement or tax relief detected",
                    )
                return (
                    True,
                    "HIGH",
                    "Fiscal / Union Budget",
                    "Union budget announcement or fiscal policy adjustment",
                )

        # Check 3: Major Policy & Regulatory Changes (Govt, RBI, SEBI)
        for pat in POLICY_REGULATORY_KEYWORDS:
            if re.search(pat, lower):
                return (
                    True,
                    "HIGH",
                    "Major Policy / Regulatory",
                    "Major policy, regulatory decision, or economic reform detected",
                )

        # Check 4: Systemic Crash / Black Swan Shocks
        for pat in CRASH_SHOCK_KEYWORDS:
            if re.search(pat, lower):
                return (
                    True,
                    "HIGH",
                    "Systemic Shock / Market Alert",
                    "Severe market volatility, crash risk, or macroeconomic shock",
                )

        # Check 5: Bullish Catalysts & Record Rallies
        for pat in BULLISH_CATALYST_KEYWORDS:
            if re.search(pat, lower):
                return (
                    True,
                    "HIGH",
                    "Macro Bullish Catalyst",
                    "Record high market rally or major positive macro catalyst",
                )

        # Check for moderate sector / corporate impact
        moderate_terms = ["earnings", "quarterly profit", "gdp", "inflation", "crude", "rupee"]
        if any(term in lower for term in moderate_terms):
            return False, "MEDIUM", "Corporate / Macro Trend", "Standard market or sector trend"

        return False, "LOW", "General Market News", "Routine market reporting"

    def _score_sentiment(
        self, text: str, category: str, is_drastic: bool
    ) -> tuple[str, float]:
        """Compute sentiment polarity score and label for news text.

        Args:
            text (str): Combined title and description text.
            category (str): Detected catalyst category.
            is_drastic (bool): Whether the item is a drastic market catalyst.

        Returns:
            tuple[str, float]: (sentiment_label, numerical_score_between_-1_and_1).
        """
        words = re.findall(r"\b[a-z]{3,}\b", text.lower())
        bull_hits = sum(1 for w in words if w in BULLISH_WORDS)
        bear_hits = sum(1 for w in words if w in BEARISH_WORDS)

        # Category-based priors
        category_bias = 0.0
        if "War" in category:
            category_bias -= 0.5
        elif "Diplomacy" in category:
            category_bias += 0.3
        elif "Favourable" in category:
            category_bias += 0.5
        elif "Shock" in category:
            category_bias -= 0.6
        elif "Bullish Catalyst" in category:
            category_bias += 0.5

        total_hits = bull_hits + bear_hits
        if total_hits > 0:
            lexicon_score = (bull_hits - bear_hits) / total_hits
        else:
            lexicon_score = 0.0

        combined_score = (lexicon_score * 0.7) + (category_bias * 0.3)
        # Clamp to [-1.0, 1.0]
        final_score = max(-1.0, min(1.0, round(combined_score, 2)))

        if final_score >= 0.15:
            sentiment_label = "BULLISH"
        elif final_score <= -0.15:
            sentiment_label = "BEARISH"
        else:
            sentiment_label = "NEUTRAL"

        return sentiment_label, final_score

    def fetch_feed_items(
        self, feed_name: str, feed_url: str, max_items: int = 15
    ) -> list[MarketNewsItem]:
        """Fetch and parse news items from a single RSS feed endpoint.

        Args:
            feed_name (str): Identifier name for the feed.
            feed_url (str): Remote URL hosting RSS XML feed.
            max_items (int): Upper bound on items to parse from this feed.

        Returns:
            list[MarketNewsItem]: List of parsed and scored news items.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        try:
            resp = requests.get(feed_url, headers=headers, timeout=6)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except (requests.RequestException, ET.ParseError) as err:
            print(f"Warning: Could not fetch RSS feed '{feed_name}': {err}")
            return []

        parsed_items: list[MarketNewsItem] = []
        # Support standard RSS <item> and Atom <entry>
        items = root.findall(".//item")
        if not items:
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

        for elem in items[:max_items]:
            raw_title = ""
            for tag in ["title", "{http://www.w3.org/2005/Atom}title"]:
                child = elem.find(tag)
                if child is not None and child.text:
                    raw_title = child.text
                    break

            raw_desc = ""
            for tag in [
                "description",
                "summary",
                "{http://www.w3.org/2005/Atom}summary",
            ]:
                child = elem.find(tag)
                if child is not None and child.text:
                    raw_desc = child.text
                    break

            link = ""
            for tag in ["link", "{http://www.w3.org/2005/Atom}link"]:
                child = elem.find(tag)
                if child is not None:
                    link = child.text or child.get("href", "")
                    if link:
                        break

            pub_date = ""
            for tag in [
                "pubDate",
                "published",
                "{http://www.w3.org/2005/Atom}published",
            ]:
                child = elem.find(tag)
                if child is not None and child.text:
                    pub_date = child.text
                    break

            clean_title = self._clean_html(raw_title)
            clean_desc = self._clean_html(raw_desc)

            if not clean_title:
                continue

            full_text = f"{clean_title}. {clean_desc}"
            is_drastic, impact, category, reason = self._classify_catalyst(full_text)
            sentiment, score = self._score_sentiment(full_text, category, is_drastic)

            # Format concise pub_date string
            display_date = pub_date[:25] if pub_date else "Recently"

            news_item = MarketNewsItem(
                title=clean_title,
                description=clean_desc,
                link=link or "",
                pub_date=display_date,
                source=feed_name,
                sentiment=sentiment,
                sentiment_score=score,
                impact_level=impact,
                is_drastic=is_drastic,
                catalyst_category=category,
                catalyst_reason=reason,
            )
            parsed_items.append(news_item)

        return parsed_items

    def analyze_market_sentiment(
        self,
        specific_feed: str | None = None,
        max_per_feed: int = 12,
    ) -> MarketSentimentSummary:
        """Fetch and aggregate sentiment across RSS feeds, isolating drastic market catalysts.

        Args:
            specific_feed (str | None): Optional single feed name to query.
            max_per_feed (int): Maximum items to fetch per feed.

        Returns:
            MarketSentimentSummary: Comprehensive market sentiment report.
        """
        all_items: list[MarketNewsItem] = []
        feeds_to_fetch = (
            {specific_feed: self.feeds[specific_feed]}
            if specific_feed and specific_feed in self.feeds
            else self.feeds
        )

        for name, url in feeds_to_fetch.items():
            feed_items = self.fetch_feed_items(name, url, max_items=max_per_feed)
            all_items.extend(feed_items)

        # Deduplicate headlines based on normalized title prefix
        seen_titles: set[str] = set()
        unique_items: list[MarketNewsItem] = []
        for item in all_items:
            norm_key = re.sub(r"[^a-zA-Z0-9]", "", item.title.lower())[:40]
            if norm_key and norm_key not in seen_titles:
                seen_titles.add(norm_key)
                unique_items.append(item)

        # If offline or all feeds were unreachable, use fallback macro sample news
        if not unique_items:
            unique_items = self._get_fallback_news()

        # Sort: Drastic/High impact items first, then by absolute score
        unique_items.sort(
            key=lambda x: (1 if x.is_drastic else 0, abs(x.sentiment_score)),
            reverse=True,
        )

        drastic_items = [it for it in unique_items if it.is_drastic]
        bull_count = sum(1 for it in unique_items if it.sentiment == "BULLISH")
        bear_count = sum(1 for it in unique_items if it.sentiment == "BEARISH")
        neut_count = sum(1 for it in unique_items if it.sentiment == "NEUTRAL")

        # Weighted score (drastic items carry 2.5x weight)
        if unique_items:
            total_weight = 0.0
            weighted_sum = 0.0
            for it in unique_items:
                w = 2.5 if it.is_drastic else 1.0
                weighted_sum += it.sentiment_score * w
                total_weight += w
            avg_score = round(weighted_sum / max(1.0, total_weight), 2)
        else:
            avg_score = 0.0

        if avg_score >= 0.25:
            overall_label = "BULLISH"
        elif avg_score >= 0.08:
            overall_label = "MODERATELY BULLISH"
        elif avg_score <= -0.25:
            overall_label = "BEARISH"
        elif avg_score <= -0.08:
            overall_label = "CAUTIOUS / BEARISH"
        else:
            overall_label = "NEUTRAL"

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Synthesize headline
        if drastic_items:
            top_catalyst = drastic_items[0]
            summary_hl = (
                f"[ALERT] {len(drastic_items)} High-Impact Catalyst(s) Detected | "
                f"Top Mover: {top_catalyst.catalyst_category} ({top_catalyst.sentiment})"
            )
        else:
            summary_hl = (
                f"Market Sentiment is {overall_label} "
                f"({bull_count} Bullish, {bear_count} Bearish, {neut_count} Neutral)"
            )

        return MarketSentimentSummary(
            overall_sentiment=overall_label,
            sentiment_score=avg_score,
            bullish_count=bull_count,
            bearish_count=bear_count,
            neutral_count=neut_count,
            drastic_events_count=len(drastic_items),
            high_impact_items=drastic_items,
            all_items=unique_items,
            timestamp=now_str,
            summary_headline=summary_hl,
        )

    def _get_fallback_news(self) -> list[MarketNewsItem]:
        """Provide simulated macro news catalysts if network is unavailable.

        Returns:
            list[MarketNewsItem]: Default sample news items illustrating drastic catalysts.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        sample_headlines = [
            (
                "Union Budget: Finance Minister announces major corporate tax cut and capex boost",
                "Union budget provides substantial tax relief and infrastructure stimulus.",
                "Fiscal / Budget (Favourable)",
                "Favourable union budget announcement or tax relief detected",
                "BULLISH",
                0.75,
                "HIGH",
                True,
            ),
            (
                "Geopolitical Escalation: Fresh airstrikes in shipping strait spur crude surge",
                "Rising military conflict threatens global oil supply routes and energy imports.",
                "Geopolitical Risk / War",
                "Geopolitical conflict, military action, or war tension detected",
                "BEARISH",
                -0.80,
                "HIGH",
                True,
            ),
            (
                "Cabinet approves major policy overhaul in renewable energy and green FDI norms",
                "New government policy unlocks 100% automatic FDI in clean power manufacturing.",
                "Major Policy / Regulatory",
                "Major policy, regulatory decision, or economic reform detected",
                "BULLISH",
                0.60,
                "HIGH",
                True,
            ),
            (
                "RBI Monetary Policy: MPC votes to maintain repo rates amid inflation watch",
                "Central bank keeps interest rate unchanged at 6.50% pointing to steady growth.",
                "Major Policy / Regulatory",
                "Monetary policy review and interest rate decision",
                "NEUTRAL",
                0.05,
                "MEDIUM",
                False,
            ),
        ]
        items = []
        for title, desc, cat, rsn, sent, score, imp, drastic in sample_headlines:
            items.append(
                MarketNewsItem(
                    title=title,
                    description=desc,
                    link="https://economictimes.indiatimes.com",
                    pub_date=now_str,
                    source="Market Archive (Fallback)",
                    sentiment=sent,
                    sentiment_score=score,
                    impact_level=imp,
                    is_drastic=drastic,
                    catalyst_category=cat,
                    catalyst_reason=rsn,
                )
            )
        return items
