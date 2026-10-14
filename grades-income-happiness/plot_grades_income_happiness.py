"""고교 내신 · 수능 · 대학 학점에 따른 소득 수준과 행복도 그래프.

성적과 소득·행복을 한 번에 담은 공개 데이터가 없어서, 연구 결과를 바탕으로
가상의 출생 코호트(40만 명)를 시뮬레이션한 뒤 성적 구간별로 집계한다.

보정에 쓴 근거 (대략적인 크기만 맞춤):
  - 4년제 졸업자 안에서 수능 1 표준편차 상승 → 임금 약 +7% (한국노동패널 KLIPS 연구)
  - 대학 학점과 임금은 양(+)의 관계지만 크기는 작음 (GOMS 기반 연구, 해외 메타분석)
  - 한국인 평균 삶의 만족도 약 6.4점 / 10점 (통계청 「국민 삶의 질 2024」)
  - 행복은 log(소득)에 비례해 완만히 증가 (Killingsworth, Kahneman & Mellers, 2023)

실행:  python plot_grades_income_happiness.py
출력:  income_by_grades.png, happiness_by_grades.png (이 파일과 같은 폴더)
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter

OUT_DIR = Path(__file__).resolve().parent
N = 400_000
SEED = 42

# 색/서체 토큰
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_3 = "#8a8984"
GRID = "#e6e5e0"
INCOME_COLOR = "#2a78d6"
HAPPY_COLOR = "#eb6834"


def setup_style():
    for name in ("NanumGothic", "Noto Sans CJK KR", "Malgun Gothic", "AppleGothic"):
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams.update({
        "axes.unicode_minus": False,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "font.size": 10.5,
    })


def pct_rank(x):
    """0~100 백분위 (클수록 상위)."""
    return x.argsort().argsort() / (len(x) - 1) * 100


def simulate(rng):
    s = rng.standard_normal(N)                      # 가정 배경(SES)
    g = 0.3 * s + np.sqrt(1 - 0.09) * rng.standard_normal(N)  # 인지능력
    c = rng.standard_normal(N)                      # 성실성

    # 고교 내신: 성실성 비중이 큼. 9등급제 누적 비율 4/11/23/40/60/77/89/96%
    naesin_pct = pct_rank(0.55 * g + 0.50 * c + 0.20 * s + 0.55 * rng.standard_normal(N))
    cuts = np.array([4, 11, 23, 40, 60, 77, 89, 96])
    naesin_grade = 1 + np.searchsorted(cuts, 100 - naesin_pct, side="right")

    # 수능: 인지능력 비중이 큼
    suneung_pct = pct_rank(0.80 * g + 0.25 * c + 0.30 * s + 0.45 * rng.standard_normal(N))

    # 4년제 졸업: 대략 상위 50%
    college = pct_rank(suneung_pct + 25 * rng.standard_normal(N)) >= 50
    # 대학 서열 프리미엄: 졸업자 안에서 수능 상위일수록 커짐
    tier = np.where(college, 0.12 * ((suneung_pct - 50).clip(0) / 50) ** 2, 0)

    # 대학 학점(4.5 만점): 성실성 비중이 큼, 졸업자만
    gpa_z = 0.35 * g + 0.55 * c + 0.75 * rng.standard_normal(N)
    gpa = np.where(college, (3.45 + 0.45 * gpa_z / gpa_z.std()).clip(1.8, 4.5), np.nan)

    # 40세 무렵 연소득(만원), 로그정규
    log_inc = (0.09 * g + 0.08 * c + 0.08 * s + 0.15 * college + tier
               + 0.55 * rng.standard_normal(N))
    log_inc += np.log(4000) - np.median(log_inc)
    income = np.exp(log_inc)

    # 삶의 만족도(0~10): log(소득) 비례 + 성실성·배경의 작은 효과 + 큰 개인차
    happy = (6.4 + 0.45 * (log_inc - np.log(4000)) + 0.15 * c + 0.10 * s
             + 1.7 * rng.standard_normal(N))
    happy = happy.clip(0, 10)

    return dict(naesin_grade=naesin_grade, suneung_pct=suneung_pct, college=college,
                gpa=gpa, income=income, log_inc=log_inc, happy=happy)


def binned(x, y, edges, stat):
    """구간별 [중심/라벨용 값, 중심통계, P25, P75]."""
    idx = np.digitize(x, edges[1:-1])
    rows = []
    for i in range(len(edges) - 1):
        yi = y[idx == i]
        rows.append((stat(yi), *np.percentile(yi, [25, 75])))
    return np.array(rows)


def panels(d):
    """세 가지 성적 축: (제목, 부제, x위치, x라벨, 마스크, 구간화 함수)."""
    grades = np.arange(9, 0, -1)  # 왼쪽=낮은 성적, 오른쪽=높은 성적
    sn_edges = np.arange(0, 101, 10.0)
    sn_edges[-1] = 100.001
    gpa_edges = np.array([1.8, 2.75, 3.0, 3.25, 3.5, 3.75, 4.0, 4.25, 4.501])
    gpa_labels = ["<2.75", "2.75", "3.0", "3.25", "3.5", "3.75", "4.0", "4.25+"]

    def by_grade(y, stat):
        return np.array([(stat(y[d["naesin_grade"] == k]),
                          *np.percentile(y[d["naesin_grade"] == k], [25, 75])) for k in grades])

    return [
        ("고교 내신 등급", "9등급제 · 전체 코호트", np.arange(9),
         [f"{k}" for k in grades], "내신 등급 (오른쪽이 상위)",
         lambda y, stat: by_grade(y, stat)),
        ("수능 백분위", "전체 응시자", np.arange(10),
         [f"{int(a)}" if a < 90 else "90+" for a in sn_edges[:-1]], "수능 백분위 구간 시작값",
         lambda y, stat: binned(d["suneung_pct"], y, sn_edges, stat)),
        ("대학 학점 (4.5 만점)", "4년제 졸업자만", np.arange(len(gpa_labels)),
         gpa_labels, "평균 평점 구간",
         lambda y, stat: binned(d["gpa"][d["college"]], y[d["college"]], gpa_edges, stat)),
    ]


def draw_panel(ax, xs, rows, color, fmt):
    mid, lo, hi = rows.T
    ax.fill_between(xs, lo, hi, color=color, alpha=0.14, linewidth=0)
    ax.plot(xs, mid, color=color, linewidth=2, marker="o", markersize=6.5,
            markeredgecolor=SURFACE, markeredgewidth=1.6, zorder=3)
    for i, ha in ((0, "left"), (-1, "right")):
        ax.annotate(fmt(mid[i]), (xs[i], mid[i]), xytext=(0, 9), textcoords="offset points",
                    ha=ha, va="bottom", color=INK, fontsize=10, fontweight="semibold")


def footer(fig, extra):
    fig.text(0.012, 0.015,
             "※ 실제 통계가 아니라, 연구 결과(KLIPS·KEEP 수능-임금 연구, 통계청 국민 삶의 질, "
             "Killingsworth 외 2023)에 맞춰 만든 시뮬레이션 모델(n=40만)의 추정치입니다.\n"
             f"   선 = {extra}, 음영 = 사분위 범위(25~75%). 같은 성적 안에서도 개인차가 훨씬 크다는 점에 주의.",
             fontsize=8.5, color=INK_3, va="bottom")


def plot_income(d):
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.6), sharey=True)
    fmt = lambda v: f"{v:,.0f}만"
    for ax, (title, sub, xs, xl, xlabel, agg) in zip(axes, panels(d)):
        rows = agg(d["income"], np.median)
        draw_panel(ax, xs, rows, INCOME_COLOR, fmt)
        ax.set_title(f"{title}\n", loc="left", fontsize=13, fontweight="semibold")
        ax.text(0, 1.02, sub, transform=ax.transAxes, color=INK_2, fontsize=9.5)
        ax.set_xticks(xs, xl)
        ax.set_xlabel(xlabel)
        ratio = rows[-1, 0] / rows[0, 0]
        ax.text(0.03, 0.95, f"최상위 / 최하위 ≈ {ratio:.1f}배", transform=ax.transAxes,
                color=INK_2, fontsize=10, va="top")
    axes[0].set_ylabel("40세 무렵 연소득 (만원)")
    axes[0].yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    axes[0].set_ylim(0, 10000)
    fig.suptitle("성적에 따른 소득 수준", x=0.012, ha="left", fontsize=17, fontweight="semibold",
                 color=INK)
    footer(fig, "중위 연소득")
    fig.tight_layout(rect=(0, 0.07, 1, 0.97))
    fig.savefig(OUT_DIR / "income_by_grades.png", dpi=150)
    plt.close(fig)


def plot_happiness(d):
    fig, axes = plt.subplots(1, 4, figsize=(19, 5.6), sharey=True,
                             gridspec_kw={"width_ratios": [1, 1, 1, 1]})
    fmt = lambda v: f"{v:.1f}점"
    for ax, (title, sub, xs, xl, xlabel, agg) in zip(axes, panels(d)):
        rows = agg(d["happy"], np.mean)
        draw_panel(ax, xs, rows, HAPPY_COLOR, fmt)
        ax.set_title(f"{title}\n", loc="left", fontsize=13, fontweight="semibold")
        ax.text(0, 1.02, sub, transform=ax.transAxes, color=INK_2, fontsize=9.5)
        ax.set_xticks(xs, xl)
        ax.set_xlabel(xlabel)
        ax.text(0.03, 0.95, f"최상위 - 최하위 = {rows[-1, 0] - rows[0, 0]:+.2f}점",
                transform=ax.transAxes, color=INK_2, fontsize=10, va="top")

    # 참고 패널: 소득 자체에 따른 행복도 (로그 축)
    ax = axes[3]
    edges = np.percentile(d["income"], np.arange(0, 101, 10))
    edges[-1] += 1
    rows = binned(d["income"], d["happy"], edges, np.mean)
    centers = np.array([np.median(d["income"][(d["income"] >= a) & (d["income"] < b)])
                        for a, b in zip(edges[:-1], edges[1:])])
    draw_panel(ax, centers, rows, HAPPY_COLOR, fmt)
    ax.set_xscale("log")
    ticks = [1000, 2000, 4000, 8000, 16000]
    ax.set_xticks(ticks, [f"{t:,}" for t in ticks])
    ax.minorticks_off()
    ax.set_xlabel("연소득 (만원, 로그 축) · 10분위 구간")
    ax.set_title("참고: 소득 → 행복\n", loc="left", fontsize=13, fontweight="semibold")
    ax.text(0, 1.02, "소득이 2배가 될 때마다 약 +0.3점", transform=ax.transAxes,
            color=INK_2, fontsize=9.5)
    ax.text(0.03, 0.95, f"최상위 - 최하위 = {rows[-1, 0] - rows[0, 0]:+.2f}점",
            transform=ax.transAxes, color=INK_2, fontsize=10, va="top")

    axes[0].set_ylabel("삶의 만족도 (0~10점)")
    axes[0].set_ylim(3, 9)
    fig.suptitle("성적에 따른 행복도 (삶의 만족도)", x=0.009, ha="left", fontsize=17,
                 fontweight="semibold", color=INK)
    footer(fig, "평균 삶의 만족도")
    fig.tight_layout(rect=(0, 0.07, 1, 0.97))
    fig.savefig(OUT_DIR / "happiness_by_grades.png", dpi=150)
    plt.close(fig)


def print_summary(d):
    z = lambda x: (x - np.nanmean(x)) / np.nanstd(x)
    m = d["college"]
    corr = lambda a, b: np.corrcoef(a, b)[0, 1]
    beta = np.polyfit(z(d["suneung_pct"][m]), d["log_inc"][m], 1)[0]
    print(f"중위 연소득: {np.median(d['income']):,.0f}만원, 평균 만족도: {d['happy'].mean():.2f}")
    print(f"r(내신 백분위, log소득) = {corr(-d['naesin_grade'], d['log_inc']):.2f}")
    print(f"r(수능 백분위, log소득) = {corr(d['suneung_pct'], d['log_inc']):.2f}")
    print(f"r(학점, log소득 | 4년제) = {corr(d['gpa'][m], d['log_inc'][m]):.2f}")
    print(f"4년제 내 수능 1SD → 소득 {np.expm1(beta) * 100:+.1f}%")
    print(f"r(log소득, 만족도) = {corr(d['log_inc'], d['happy']):.2f}")
    print(f"r(수능 백분위, 만족도) = {corr(d['suneung_pct'], d['happy']):.2f}")


def main():
    setup_style()
    d = simulate(np.random.default_rng(SEED))
    print_summary(d)
    plot_income(d)
    plot_happiness(d)
    print(f"저장: {OUT_DIR / 'income_by_grades.png'}")
    print(f"저장: {OUT_DIR / 'happiness_by_grades.png'}")


if __name__ == "__main__":
    main()
