from decimal import Decimal


ASSESSMENT_VERSION = "RISK_PROFILE_V2"
SCORE_KEYS = ("guardian", "balanced", "growth", "opportunity")
TYPE_BY_KEY = {
    "guardian": "CAPITAL_GUARDIAN",
    "balanced": "BALANCED_SMART",
    "growth": "FUTURE_GROWTH",
    "opportunity": "OPPORTUNITY_SEEKER",
}
TYPE_TIE_ORDER = ("balanced", "guardian", "growth", "opportunity")
PROFILE_METADATA = {
    "CAPITAL_GUARDIAN": {
        "title": "محافظ سرمایه",
        "description": "حفظ اصل سرمایه، نقدشوندگی و آرامش مالی برای شما اولویت دارد.",
    },
    "BALANCED_SMART": {
        "title": "متعادل و هوشمند",
        "description": "امنیت و رشد را با تنوع، تحلیل و تصمیم‌های سنجیده ترکیب می‌کنید.",
    },
    "FUTURE_GROWTH": {
        "title": "رشدطلب آینده‌نگر",
        "description": "برای رشد بلندمدت، نوسان حساب‌شده را می‌پذیرید و صبور می‌مانید.",
    },
    "OPPORTUNITY_SEEKER": {
        "title": "فرصت‌جو",
        "description": "فرصت‌های پربازده را سریع می‌بینید و ظرفیت پذیرش ریسک بالاتری دارید.",
    },
}
ASSET_OPTIONS = {f"ASSET_{number}" for number in range(1, 8)}


def _s(guardian, balanced, growth, opportunity):
    return dict(zip(SCORE_KEYS, (guardian, balanced, growth, opportunity)))


# Kept in the same question/option order as frontend src/utils/personalityRisk.js.
QUESTION_SCORES = {
    1: {"NONE": _s(4,1,0,0), "LOW": _s(3,3,1,0), "MEDIUM": _s(1,4,3,1), "HIGH": _s(0,2,4,4)},
    3: {"STRONGLY_DISAGREE": _s(0,0,2,5), "DISAGREE": _s(0,1,4,3), "AGREE": _s(3,4,1,0), "STRONGLY_AGREE": _s(5,2,0,0)},
    4: {"EMPLOYEE": _s(2,4,2,1), "PUBLIC": _s(3,4,1,0), "BUSINESS": _s(0,2,4,4), "FREELANCE": _s(1,2,3,4), "STUDENT": _s(2,3,3,2), "RETIRED": _s(5,2,0,0), "HOMEMAKER": _s(3,3,1,0), "NO_INCOME": _s(5,1,0,0), "OTHER": _s(2,3,2,2)},
    5: {"UNDER_30": _s(4,2,1,0), "30_45": _s(3,3,2,1), "45_75": _s(2,4,3,1), "75_120": _s(1,3,4,2), "120_200": _s(1,2,4,4), "OVER_200": _s(0,2,4,5)},
    6: {"UNDER_500M": _s(4,2,1,0), "500M_1B": _s(3,3,2,1), "1B_5B": _s(2,4,3,2), "5B_15B": _s(1,3,4,3), "15B_30B": _s(1,2,4,4), "OVER_30B": _s(0,2,4,5)},
    7: {"UNDER_1Y": _s(5,2,0,1), "1_3Y": _s(3,4,2,1), "3_5Y": _s(1,4,4,2), "OVER_5Y": _s(0,2,5,4)},
    8: {"MOST": _s(5,1,0,0), "HALF": _s(4,3,1,0), "SMALL": _s(1,4,4,2), "NONE": _s(0,2,5,4)},
    9: {"SELL_ALL": _s(5,1,0,0), "SELL_PART": _s(4,3,1,0), "WAIT": _s(1,5,4,1), "BUY_MORE": _s(0,2,4,5)},
    10: {"PRESERVE": _s(5,2,0,0), "INCOME": _s(4,4,1,0), "GROWTH": _s(0,3,5,2), "HIGH_RETURN": _s(0,1,3,5)},
    11: {"5": _s(5,1,0,0), "10": _s(3,4,1,0), "20": _s(1,4,4,2), "OVER_20": _s(0,1,4,5)},
    12: {"NONE": _s(4,1,0,1), "1_3": _s(3,3,1,0), "3_6": _s(2,5,3,1), "OVER_6": _s(1,4,5,3)},
    13: {"OVER_50": _s(5,1,0,0), "30_50": _s(4,3,1,0), "10_30": _s(2,5,3,1), "UNDER_10": _s(1,3,5,4)},
    14: {"GUARANTEE": _s(5,2,0,0), "RESEARCH": _s(1,5,4,1), "ADVISOR": _s(3,4,2,0), "FAST": _s(0,1,3,5)},
    15: {"STOP": _s(5,1,0,0), "CAUTIOUS": _s(4,4,1,0), "LEARN": _s(1,5,4,1), "RECOVER": _s(0,1,2,5)},
    16: {"SAFE": _s(5,2,0,0), "BALANCED": _s(1,5,3,1), "GROWTH": _s(0,2,5,3), "AGGRESSIVE": _s(0,1,2,5)},
    17: {"UNDER_10": _s(5,3,1,0), "10_25": _s(2,5,3,1), "25_50": _s(0,2,5,3), "OVER_50": _s(0,0,2,5)},
    18: {"IGNORE": _s(4,3,1,0), "ANALYZE": _s(1,5,4,1), "GRADUAL": _s(1,3,5,3), "ENTER": _s(0,0,2,5)},
}


def largest_remainder_percentages(scores):
    total = sum(scores.values()) or 1
    exact = {key: (Decimal(scores[key]) * Decimal(100)) / Decimal(total) for key in SCORE_KEYS}
    result = {key: int(value) for key, value in exact.items()}
    remainder = 100 - sum(result.values())
    order = sorted(SCORE_KEYS, key=lambda key: (-(exact[key] % 1), SCORE_KEYS.index(key)))
    for key in order[:remainder]:
        result[key] += 1
    return result


def dominant_type_for_scores(scores):
    winner_key = max(
        TYPE_TIE_ORDER,
        key=lambda key: (scores[key], -TYPE_TIE_ORDER.index(key)),
    )
    return TYPE_BY_KEY[winner_key]


def calculate_result(answers):
    scores = {key: 0 for key in SCORE_KEYS}
    for answer in answers:
        question_id = answer["question_id"]
        if question_id == 2:
            continue
        for key, value in QUESTION_SCORES[question_id][answer["option_id"]].items():
            scores[key] += value
    percentages = largest_remainder_percentages(scores)
    return scores, percentages, dominant_type_for_scores(scores)
