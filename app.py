import streamlit as st
import streamlit.components.v1 as components  #20260410 JavaScript実行用
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import plotly.graph_objects as go
import re
from datetime import datetime, date  #20240409

from modules.utils import read_yaml
from modules.get_persona_info import get_persona_info
from modules.types import (
    ChatResponse,
    PersonaInfo,
    Catalog,
    PlanType,
    SpecialContractCategory,
    InjuryIllnessSpecialContractType,
    CoverageLevel
)
from my03_chat_with_lc import ChatWithLC, StatusFlg
from my10_generate_people_like_you_talk import GeneratePeopleLikeYouTalk


# ==============================================================================
# ボタンクリック時のコールバック関数 #20260410
# ==============================================================================
def handle_option_click(option_text: str):  #20260410
    """オプションボタンがクリックされた時の処理"""  #20260410
    st.session_state.messages.append({"role": "user", "content": option_text})  #20260410
    st.session_state.button_options = []  #20260410 選択肢を即座に消す
    st.session_state.pending_input_display = ""  #20260410 入力欄もクリア
    st.session_state.pending_ai_request = option_text  #20260410 後続の処理でAIを呼ぶフラグを立てる
    st.session_state.should_scroll_to_user = False  #20260410 新しいリクエストが来たのでスクロールフラグをリセット

def handle_plan_click(plan_name: str):  #20260410
    """プラン選択ボタンがクリックされた時の処理"""  #20260410
    st.session_state.messages.append({"role": "user", "content": f"{plan_name}プランを選択します"})  #20260410
    st.session_state.selected_radar_plan = plan_name  #20260410
    st.session_state.pending_input_display = ""  #20260410
    st.session_state.pending_ai_request = f"PLAN_{plan_name}"  #20260410 プラン選択専用のフラグ
    st.session_state.should_scroll_to_user = False  #20260410 新しいリクエストが来たのでスクロールフラグをリセット

# ==============================================================================
# 定数・設定ファイルの読み込み

# ==============================================================================

BASE_FOLDER = Path.cwd()
PARAMETERS_PATH = BASE_FOLDER / "settings" / "parameters.yaml"
PARAMETERS = read_yaml(PARAMETERS_PATH)
INPUT_FILE_PATH = BASE_FOLDER / Path(PARAMETERS["file_io"]["settings"]["scenario_list"])
OUTPUT_FILE_PATH = BASE_FOLDER / Path(PARAMETERS["file_io"]["output_file"])
COVERAGE_CATEGORY_DICT = PARAMETERS["coverage_category_dict"]



# ==============================================================================
# プランとCoverageLevelのマッピング

# ==============================================================================

COVERAGE_LEVEL_TO_PLAN = {
    CoverageLevel.ENHANCED: "松",
    CoverageLevel.STANDARD: "竹",
    CoverageLevel.BASIC: "梅",
}

PLAN_TO_COVERAGE_LEVEL = {
    "松": CoverageLevel.ENHANCED,
    "竹": CoverageLevel.STANDARD,
    "梅": CoverageLevel.BASIC,
}



# ==============================================================================
# 特約保険料表示用の定数

# ==============================================================================

SPECIAL_CONTRACT_CATEGORY_ORDER = [
    ("injury_illness_special_contracts", "病気・ケガへの備え"),
    ("cancer_special_contracts", "がん保障"),
    ("circulatory_special_contracts", "循環器病保障"),
    ("severe_disease_special_contracts", "特定重度疾病保障"),
    ("disability_special_contracts", "障害・就労不能保障"),
    ("health_promotion_special_contracts", "健康促進保障"),
]

PLAN_TYPE_TO_NAME = {
    PlanType.MATSU: "松プラン",
    PlanType.TAKE: "竹プラン",
    PlanType.UME: "梅プラン",
}



# ==============================================================================
# 年齢計算関数

# ==============================================================================

def calculate_age(birth_date) -> int:  #20240409
    """生年月日から年齢を計算"""  #20240409
    if pd.isna(birth_date):  #20240409
        return 0  #20240409
    
    if isinstance(birth_date, pd.Timestamp):  #20240409
        birth_date = birth_date.date()  #20240409
    elif isinstance(birth_date, datetime):  #20240409
        birth_date = birth_date.date()  #20240409
    elif isinstance(birth_date, str):  #20240409
        try:  #20240409
            birth_date = datetime.strptime(birth_date, '%Y-%m-%d').date()  #20240409
        except:  #20240409
            try:  #20240409
                birth_date = datetime.strptime(birth_date, '%Y年%m月%d日').date()  #20240409
            except:  #20240409
                return 0  #20240409
    elif not isinstance(birth_date, date):  #20240409
        return 0  #20240409
    
    today = date.today()  #20240409
    age = today.year - birth_date.year  #20240409
    
    if (today.month, today.day) < (birth_date.month, birth_date.day):  #20240409
        age -= 1  #20240409
    
    return age  #20240409



# ==============================================================================
# データ読み込み関数（キャッシュ付き）

# ==============================================================================

@st.cache_data
def load_persona_data() -> pd.DataFrame:
    all_excel_sheets = pd.read_excel(
        io=INPUT_FILE_PATH,
        sheet_name=None,
        engine="openpyxl"
    )
    persona_data = all_excel_sheets["ペルソナ一覧"]
    persona_data = persona_data.reset_index(drop=True)
    persona_data.index = persona_data.index + 1
    return persona_data



# ==============================================================================
# 応答解析関数

# ==============================================================================

def extract_button_options_from_response(response_text: str) -> Tuple[str, List[str]]:
    if not response_text:
        return "", []
    
    if isinstance(response_text, list):
        response_text = "\n".join(str(text) for text in response_text if text)
    else:
        response_text = str(response_text)
    
    delimiter = "\n ・"
    
    if delimiter not in response_text:
        return response_text.strip(), []
    
    parts = response_text.split(delimiter)
    main_text = parts[0].strip()
    
    options = []
    for part in parts[1:]:
        option = part.strip()
        if option:
            options.append(f"・{option}")
    
    return main_text, options



# ==============================================================================
# セッション状態の初期化

# ==============================================================================

def initialize_session_state() -> None:
    persona_data = load_persona_data()
    
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "conversation" not in st.session_state:
        st.session_state.conversation = []
    
    if "selected_persona_idx" not in st.session_state:
        st.session_state.selected_persona_idx = 0
    
    if "persona_info" not in st.session_state:
        persona_indices = persona_data.index.tolist()
        first_persona_no = persona_indices[0]
        st.session_state.persona_info = get_persona_info(persona_data, first_persona_no)
    
    if "current_persona_id" not in st.session_state:
        persona_indices = persona_data.index.tolist()
        st.session_state.current_persona_id = persona_indices[0]
    
    if "response" not in st.session_state:
        st.session_state.response = None
    
    if "catalog" not in st.session_state:
        st.session_state.catalog = None
    
    if "kitei_message" not in st.session_state:
        st.session_state.kitei_message = ""
    
    if "required_coverage_amount_adjustment_parameters" not in st.session_state:
        st.session_state.required_coverage_amount_adjustment_parameters = {}
    
    if "status_flg" not in st.session_state:
        st.session_state.status_flg = ""
    
    if "required_coverage_amount_dict" not in st.session_state:
        st.session_state.required_coverage_amount_dict = {}

    if "catalog_explanation_text" not in st.session_state:
        st.session_state.catalog_explanation_text = ""
    
    if "statistical_info_text" not in st.session_state:
        st.session_state.statistical_info_text = ""
    
    if "similar_page_list" not in st.session_state:
        st.session_state.similar_page_list = []
    
    if "most_similar_page" not in st.session_state:
        st.session_state.most_similar_page = None
    
    if "select_reason" not in st.session_state:
        st.session_state.select_reason = ""
    
    if "user_input" not in st.session_state:
        st.session_state.user_input = ""
    
    if "selected_radar_plan" not in st.session_state:
        st.session_state.selected_radar_plan = "松"

    if "ply_explanation" not in st.session_state:
        st.session_state.ply_explanation = ""

    if "customer_cluster" not in st.session_state:
        st.session_state.customer_cluster = None

    if "special_contract_cluster" not in st.session_state:
        st.session_state.special_contract_cluster = None

    if "button_options" not in st.session_state:
        st.session_state.button_options = []

    if "ply_shown" not in st.session_state:
        st.session_state.ply_shown = False

    if "response_answers" not in st.session_state:
        st.session_state.response_answers = []

    # レーダーチャートに表示する項目（初期表示時に決定）
    if "radar_visible_categories" not in st.session_state:
        st.session_state.radar_visible_categories = None

    # 選択肢から選択された内容を表示するための変数 #20240409
    if "pending_input_display" not in st.session_state:  #20240409
        st.session_state.pending_input_display = ""  #20240409

    # AIへのリクエストを遅延実行するための状態変数 #20260410
    if "pending_ai_request" not in st.session_state:  #20260410
        st.session_state.pending_ai_request = None  #20260410
    st.session_state.should_scroll_to_user = False  #20260410
    
    # 自動スクロール用のフラグ #20260410
    if "should_scroll_to_user" not in st.session_state:  #20260410
        st.session_state.should_scroll_to_user = False  #20260410


def reset_conversation_state() -> None:
    st.session_state.messages = []
    st.session_state.conversation = []
    st.session_state.response = None
    st.session_state.catalog = None
    st.session_state.kitei_message = ""
    st.session_state.required_coverage_amount_adjustment_parameters = {}
    st.session_state.required_coverage_amount_dict = {}
    st.session_state.catalog_explanation_text = ""
    st.session_state.statistical_info_text = ""
    st.session_state.similar_page_list = []
    st.session_state.most_similar_page = None
    st.session_state.select_reason = ""
    st.session_state.user_input = ""
    st.session_state.status_flg = ""
    st.session_state.selected_radar_plan = "松"
    st.session_state.ply_explanation = ""
    st.session_state.customer_cluster = None
    st.session_state.special_contract_cluster = None
    st.session_state.button_options = []
    st.session_state.ply_shown = False
    st.session_state.response_answers = []
    # レーダーチャート表示項目もリセット
    st.session_state.radar_visible_categories = None
    st.session_state.pending_input_display = ""  #20240409
    st.session_state.pending_ai_request = None  #20260410
    st.session_state.should_scroll_to_user = False  #20260410



# ==============================================================================
# 松プランの保障額に基づいて表示する項目を決定する関数

# ==============================================================================

def determine_visible_categories() -> Optional[List]:
    """
    松プラン（ENHANCED）の保障額に基づいて、レーダーチャートに表示する項目を決定する。
    0円の項目は表示しない。
    
    Returns:
        表示するカテゴリオブジェクトのリスト、またはデータがない場合はNone
    """
    coverage_dict = st.session_state.required_coverage_amount_dict
    
    if not coverage_dict:
        return None
    
    # 松プラン（ENHANCED）のデータを取得
    matsu_data = coverage_dict.get(CoverageLevel.ENHANCED)
    
    if not matsu_data:
        return None
    
    # 0円でない項目のカテゴリオブジェクトを収集
    visible_categories = []
    for category, amount in matsu_data.items():
        if float(amount or 0) > 0:
            visible_categories.append(category)
    
    return visible_categories



# ==============================================================================
# catalog から保障額を同期する関数

# ==============================================================================
def sync_coverage_dict_from_catalog() -> None:
    """
    catalog の Plan.coverage_amount_by_category があれば、
    required_coverage_amount_dict を catalog の値で同期（上書き）する。
    また、初回のみレーダーチャートに表示する項目を決定する。
    """
    catalog = st.session_state.catalog
    if not catalog:
        return

    plan_to_level = {
        PlanType.MATSU: CoverageLevel.ENHANCED,
        PlanType.TAKE: CoverageLevel.STANDARD,
        PlanType.UME: CoverageLevel.BASIC,
    }

    updated_dict = {}
    for plan_type, coverage_level in plan_to_level.items():
        plan = catalog.get(plan_type)
        if plan and getattr(plan, "coverage_amount_by_category", None):
            updated_dict[coverage_level] = dict(plan.coverage_amount_by_category)

    if updated_dict:
        st.session_state.required_coverage_amount_dict = updated_dict
    
    # 初回のみ表示項目を決定（まだ設定されていない場合のみ）
    if st.session_state.radar_visible_categories is None:
        st.session_state.radar_visible_categories = determine_visible_categories()




# ==============================================================================
# レーダーチャート作成関数

# ==============================================================================

def create_coverage_radar_chart(plan_name: str) -> go.Figure:
    coverage_dict = st.session_state.required_coverage_amount_dict
    # 表示する項目のリストを取得
    visible_categories = st.session_state.radar_visible_categories

    if not coverage_dict:
        fig = go.Figure()
        fig.add_annotation(
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=14, color="#666666"),
            align="center"
        )
        fig.update_layout(
            height=280,
            margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor='#ffffff',
            plot_bgcolor='#ffffff'
        )
        return fig

    coverage_level = PLAN_TO_COVERAGE_LEVEL.get(plan_name)

    if coverage_level is None or coverage_level not in coverage_dict:
        fig = go.Figure()
        fig.add_annotation(
            text=f"{plan_name}プランのデータがありません",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=14, color="#666666"),
            align="center"
        )
        fig.update_layout(
            height=280,
            margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor='#ffffff',
            plot_bgcolor='#ffffff'
        )
        return fig

    plan_data = coverage_dict[coverage_level]

    base_labels: List[str] = []
    values_yen: List[float] = []
    values_man: List[float] = []

    for category, amount in plan_data.items():
        # 表示項目が設定されている場合、その項目のみ表示
        if visible_categories is not None and category not in visible_categories:
            continue
        
        label = category.value if hasattr(category, "value") else str(category)
        base_labels.append(label)

        amt = float(amount or 0)
        values_yen.append(amt)
        values_man.append(amt / 10000.0)

    # 表示する項目がない場合のハンドリング
    if not base_labels:
        fig = go.Figure()
        fig.add_annotation(
            text="表示する保障項目がありません",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=14, color="#666666"),
            align="center"
        )
        fig.update_layout(
            height=280,
            margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor='#ffffff',
            plot_bgcolor='#ffffff'
        )
        return fig

    theta_labels = [f"{lbl}<br>{man:,.0f}万円" for lbl, man in zip(base_labels, values_man)]

    # 松プランの最大値計算もフィルタリングを適用
    if CoverageLevel.ENHANCED in coverage_dict:
        max_plan_data = coverage_dict[CoverageLevel.ENHANCED]
        max_values = []
        for category, amount in plan_data.items():
            # 表示項目のみを対象とする
            if visible_categories is not None and category not in visible_categories:
                continue
            max_values.append(float(max_plan_data.get(category, 1) or 0))
        normalized_values = [
            (v / mv) * 100 if mv > 0 else 0
            for v, mv in zip(values_yen, max_values)
        ]
    else:
        max_val = max(values_yen) if values_yen and max(values_yen) > 0 else 1
        normalized_values = [(v / max_val) * 100 for v in values_yen]

    theta_closed = theta_labels + [theta_labels[0]]
    normalized_closed = normalized_values + [normalized_values[0]]
    values_man_closed = values_man + [values_man[0]]

    plan_colors = {
        "松": {"fill": "rgba(41, 163, 131, 0.25)", "line": "#29A383"},
        "竹": {"fill": "rgba(250, 191, 0, 0.25)", "line": "#FABF00"},
        "梅": {"fill": "rgba(102, 126, 234, 0.25)", "line": "#667eea"},
    }
    color_config = plan_colors.get(plan_name, plan_colors["松"])

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=normalized_closed,
        theta=theta_closed,
        fill="toself",
        fillcolor=color_config["fill"],
        line=dict(color=color_config["line"], width=2),
        name=f"{plan_name}プラン",
        hovertemplate="%{theta}<br>保障額: %{customdata:,.0f}万円<br>松プラン比: %{r:.1f}%<extra></extra>",
        customdata=values_man_closed
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickvals=[0, 25, 50, 75, 100],
                ticktext=["0%", "25%", "50%", "75%", "100%"],
                tickfont=dict(size=11, color="#666666"),  #20240409 9から11に変更
                gridcolor="#e9ecef",
            ),
            angularaxis=dict(
                tickfont=dict(size=13, color="#333333", family="Arial Black"),  #20240409 10から13に変更、フォントを太字に
                gridcolor="#e9ecef",
            ),
            bgcolor="#ffffff",
        ),
        showlegend=False,
        height=320,  #20240409 280から320に変更（文字が大きくなった分、高さも調整）
        margin=dict(l=60, r=60, t=40, b=40),  #20240409 マージンを調整
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
    )

    return fig


def get_coverage_data_with_categories(plan_name: str) -> List[Tuple]:
    """
    指定プランの保障額データをカテゴリオブジェクトと共に取得
    松プランで0円の項目はフィルタリング
    """
    coverage_dict = st.session_state.required_coverage_amount_dict
    # 表示する項目のリストを取得
    visible_categories = st.session_state.radar_visible_categories
    
    if not coverage_dict:
        return []
    
    coverage_level = PLAN_TO_COVERAGE_LEVEL.get(plan_name)
    
    if coverage_level is None or coverage_level not in coverage_dict:
        return []
    
    plan_data = coverage_dict[coverage_level]
    
    result = []
    for category, amount in plan_data.items():
        # 表示項目が設定されている場合、その項目のみ表示
        if visible_categories is not None and category not in visible_categories:
            continue
        
        if hasattr(category, 'value'):
            label = category.value
        else:
            label = str(category)
        result.append((category, label, amount))
    
    return result



# ==============================================================================
# 特約保険料データ抽出関数

# ==============================================================================

def get_special_contract_data() -> Dict:
    catalog = st.session_state.catalog
    
    if not catalog:
        return {}
    
    result = {}
    
    for plan_type in [PlanType.MATSU, PlanType.TAKE, PlanType.UME]:
        plan = catalog.get(plan_type)
        if not plan:
            continue
        
        plan_name = PLAN_TYPE_TO_NAME.get(plan_type, str(plan_type))
        result[plan_name] = {
            "total_premium": 0,
            "categories": {}
        }
        
        total_premium = 0
        
        for attr_name, category_name in SPECIAL_CONTRACT_CATEGORY_ORDER:
            contracts = getattr(plan, attr_name, {})
            if not contracts:
                continue
            
            result[plan_name]["categories"][category_name] = []
            
            for contract_type, contract_info in contracts.items():
                contract_name = contract_type.value if hasattr(contract_type, 'value') else str(contract_type)
                benefit_amount = contract_info.benefit_amount_yen
                premium = contract_info.premium_yen
                
                total_premium += premium
                
                if benefit_amount > 0:
                    benefit_display = f"{benefit_amount:,}"
                else:
                    benefit_display = "付加"
                
                result[plan_name]["categories"][category_name].append({
                    "name": contract_name,
                    "benefit": benefit_display,
                    "premium": premium
                })
        
        result[plan_name]["total_premium"] = total_premium
    
    return result


@st.dialog("特約保険料金額確認", width="large")
def show_special_contract_premium_dialog():
    data = get_special_contract_data()
    
    if not data:
        st.warning("データがありません。ドラフトプランを作成してください。")
        return
    
    plan_names = ["松プラン", "竹プラン", "梅プラン"]
    available_plans = [p for p in plan_names if p in data]
    
    st.markdown("### 📊 保険料サマリー")
    
    cols = st.columns(len(available_plans))
    for i, plan_name in enumerate(available_plans):
        with cols[i]:
            total = data[plan_name]["total_premium"]
            if "松" in plan_name:
                color = "#29A383"
            elif "竹" in plan_name:
                color = "#FABF00"
            else:
                color = "#667eea"
            
            st.markdown(f"""
            <div style="
                background-color: {color}20;
                border: 2px solid {color};
                border-radius: 10px;
                padding: 15px;
                text-align: center;
            ">
                <div style="font-weight: 600; color: {color}; font-size: 1rem;">{plan_name}</div>
                <div style="font-size: 1.5rem; font-weight: 700; color: #333;">{total:,}円</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.divider()
    
    st.markdown("### 📋 特約詳細")
    
    ordered_categories = [cat_name for _, cat_name in SPECIAL_CONTRACT_CATEGORY_ORDER]
    
    for category in ordered_categories:
        has_category = any(
            category in data[plan_name]["categories"] 
            for plan_name in available_plans 
            if plan_name in data
        )
        
        if not has_category:
            continue
        
        st.markdown(f"**🔹 {category}**")
        
        all_contracts = {}
        for plan_name in available_plans:
            if plan_name in data and category in data[plan_name]["categories"]:
                for contract in data[plan_name]["categories"][category]:
                    if contract["name"] not in all_contracts:
                        all_contracts[contract["name"]] = {}
                    all_contracts[contract["name"]][plan_name] = contract
        
        table_rows = []
        for contract_name, contract_data in all_contracts.items():
            row = {"特約名": contract_name}
            for plan_name in available_plans:
                if plan_name in contract_data:
                    contract = contract_data[plan_name]
                    row[f"{plan_name}_付加内容"] = contract["benefit"]
                    row[f"{plan_name}_保険料"] = f"{contract['premium']:,}"
                else:
                    row[f"{plan_name}_付加内容"] = "-"
                    row[f"{plan_name}_保険料"] = "-"
            table_rows.append(row)
        
        if table_rows:
            thead = "<thead><tr>"
            thead += '<th rowspan="2" style="min-width:160px; text-align:center; vertical-align:middle;">特約名</th>'
            for p in available_plans:
                thead += f'<th colspan="1" style="text-align:center; min-width:140px;">{p}</th>'
            thead += "</tr><tr>"
            for _ in available_plans:
                thead += '<th style="text-align:center; font-size:0.85rem; color:#666;">付加内容<br>保険料</th>'
            thead += "</tr></thead>"

            tbody = "<tbody>"
            for row in table_rows:
                tbody += "<tr>"
                tbody += f'<td style="font-weight:600; text-align:left;">{row["特約名"]}</td>'
                for p in available_plans:
                    benefit = row.get(f"{p}_付加内容", "-")
                    premium = row.get(f"{p}_保険料", "-")
                    tbody += f'<td style="text-align:center;">{benefit}<br><span style="font-weight:700;">{premium}</span></td>'
                tbody += "</tr>"
            tbody += "</tbody>"

            st.markdown(f"""
                <style>
                .sc-table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-bottom: 1rem; }}
                .sc-table th, .sc-table td {{ border: 1px solid #e9ecef; padding: 10px 12px; vertical-align: middle; }}
                .sc-table thead th {{ background: #f8f9fa; font-weight: 600; }}
                .sc-table tbody tr:hover {{ background-color: #f8f9fa; }}
                </style>
                <table class="sc-table">{thead}{tbody}</table>
            """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("✕ 閉じる", key="close_premium_dialog", use_container_width=True):
            st.rerun()



# ==============================================================================
# チャットAPI呼び出し関数

# ==============================================================================

def call_chat_api(user_message: str) -> str:
    persona_info = st.session_state.persona_info
    conversation = st.session_state.conversation.copy()
    catalog = st.session_state.catalog
    required_coverage_amount_adjustment_parameters = (
        st.session_state.required_coverage_amount_adjustment_parameters.copy()
    )
    required_coverage_amount_dict = (
        st.session_state.required_coverage_amount_dict.copy()
    )
    
    user_prompt = user_message
    chat_lc = ChatWithLC(persona_info, conversation)
    
    (
        response,
        catalog,
        required_coverage_amount_adjustment_parameters,
        conversation,
        catalog_explanation_text,
        kitei_message,
        response_texts,
        required_coverage_amount_dict,
        similar_page_list,
        most_similar_page,
        select_reason,
        statistical_info_text,
        status_flg
    ) = chat_lc.run(
        user_prompt,
        catalog,
        required_coverage_amount_adjustment_parameters,
        required_coverage_amount_dict
    )

    
    st.session_state.response = response
    st.session_state.catalog = catalog
    st.session_state.conversation = conversation
    st.session_state.kitei_message = kitei_message
    st.session_state.required_coverage_amount_adjustment_parameters = (
        required_coverage_amount_adjustment_parameters
    )
    st.session_state.required_coverage_amount_dict = required_coverage_amount_dict
    
    # catalog から実際の保障額を同期
    sync_coverage_dict_from_catalog()
    
    st.session_state.catalog_explanation_text = catalog_explanation_text
    st.session_state.statistical_info_text = statistical_info_text
    st.session_state.similar_page_list = similar_page_list
    st.session_state.most_similar_page = most_similar_page
    st.session_state.select_reason = select_reason
    st.session_state.status_flg = status_flg
    
    if response_texts:
        if isinstance(response_texts, list):
            ai_response = "\n".join(str(text) for text in response_texts if text)
        else:
            ai_response = str(response_texts)
    elif response and hasattr(response, 'message'):
        ai_response = response.message
    else:
        ai_response = "応答を取得できませんでした。"

    if catalog and catalog.get(PlanType.TAKE):
        highest_coverage_category, coverage_level = (
            catalog[PlanType.TAKE].get_highest_coverage_category()
        )
        target_perspective = highest_coverage_category.value
    
    if response_texts:
        if isinstance(response_texts, list):
            response_texts_str = "\n".join(str(text) for text in response_texts if text)
        else:
            response_texts_str = str(response_texts)
    else:
        response_texts_str = ""
    
    main_text, extracted_options = extract_button_options_from_response(response_texts_str)
    
    if extracted_options:
        st.session_state.button_options = extracted_options
        ai_response = main_text
    else:
        st.session_state.button_options = []
    
    st.session_state.response_answers.append({
        "user_input": user_message,
        "ai_response": ai_response,
        "status_flg": status_flg,
    })
    
    return ai_response



# ==============================================================================
# PLY提案文生成関数

# ==============================================================================

def generate_ply_proposal(plan_type: PlanType = PlanType.TAKE) -> str:
    catalog = st.session_state.catalog
    persona_info = st.session_state.persona_info
    
    if not catalog:
        return "⚠️ プラン情報が設定されていないため、提案文を生成できません。"
    
    plan = catalog.get(plan_type)
    if not plan:
        plan_name = {
            PlanType.MATSU: "松",
            PlanType.TAKE: "竹",
            PlanType.UME: "梅"
        }.get(plan_type, str(plan_type))
        return f"⚠️ {plan_name}プランが設定されていないため、提案文を生成できません。"
    
    try:
        ply_generator = GeneratePeopleLikeYouTalk(plan, persona_info)
        explanation_ply, customer_cluster, special_contract_cluster = ply_generator.run()
        
        st.session_state.ply_explanation = explanation_ply
        st.session_state.customer_cluster = customer_cluster
        st.session_state.special_contract_cluster = special_contract_cluster
        
        return explanation_ply
        
    except Exception as e:
        error_message = f"提案文の生成中にエラーが発生しました: {str(e)}"
        return error_message


def change_persona(new_persona_idx: int, persona_data: pd.DataFrame) -> None:
    persona_indices = persona_data.index.tolist()
    persona_no = persona_indices[new_persona_idx]
    
    st.session_state.persona_info = get_persona_info(persona_data, persona_no)
    st.session_state.current_persona_id = persona_no
    st.session_state.selected_persona_idx = new_persona_idx
    
    reset_conversation_state()



# ==============================================================================
# ページ設定

# ==============================================================================

st.set_page_config(
    page_title="AI Chat App",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded"
)



# ==============================================================================
# セッション状態の初期化を実行

# ==============================================================================

initialize_session_state()



# ==============================================================================
# カスタムCSS

# ==============================================================================

st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { overflow: hidden !important; }  #20260410 画面全体のスクロールを無効化
    [data-testid="stSidebar"] { position: relative !important; height: 100vh !important; background-color: #f8f9fa; border-right: 1px solid #e9ecef; } /* #20260410 幅と表示の強制を解除 */
    [data-testid="stSidebar"] > div:first-child { position: relative !important; height: 100vh !important; overflow-y: auto !important; }
    [data-testid="stSidebarContent"] { overflow-y: auto !important; height: 100% !important; }
    .main .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; padding-left: 0.25rem !important; padding-right: 1rem !important; max-width: 100% !important; }
    header[data-testid="stHeader"] { display: none !important; }  #20260410 ヘッダーの余白を完全に削除
    h1 { font-size: 1.5rem !important; font-weight: 600 !important; color: #1a1a2e !important; margin-bottom: 0.5rem !important; }
    h2, h3, .stSubheader { font-size: 1rem !important; font-weight: 600 !important; color: #16213e !important; margin-bottom: 0.5rem !important; }
    [data-testid="stSidebar"] .stButton > button { background-color: #ffffff; border: 1px solid #dee2e6; color: #495057; font-weight: 500; font-size: 0.875rem; padding: 0.5rem 1rem; border-radius: 6px; }
    [data-testid="stSidebar"] .stButton > button:hover { background-color: #e9ecef; border-color: #adb5bd; }
    [data-testid="stSidebar"] .stButton > button[kind="primary"] { background-color: #29A383 !important; border-color: #29A383 !important; color: white !important; }
    .stChatMessage { padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 0.5rem; }
    hr { margin: 0.75rem 0; border-color: #e9ecef; }
    .info-card { background-color: #ffffff; border: 1px solid #e9ecef; border-radius: 8px; padding: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .info-card table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    .info-card td { padding: 0.4rem 0.5rem; border-bottom: 1px solid #f1f3f4; }
    .info-card .label { font-weight: 600; color: #495057; width: 40%; }
    .info-card .value { color: #212529; }
    .info-card .highlight-value { font-weight: 600; color: #29A383; }
    .sidebar-header { font-size: 0.875rem; font-weight: 600; color: #495057; margin-bottom: 0.75rem; padding-bottom: 0.5rem; border-bottom: 2px solid #29A383; }
    .main .stButton > button[kind="primary"] { background-color: #29A383 !important; border-color: #29A383 !important; color: white !important; }
    .stButton > button:disabled { background-color: #e9ecef !important; border-color: #dee2e6 !important; color: #adb5bd !important; }
    /* 保障額詳細表示用のスタイル */
    .coverage-detail-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    .coverage-detail-table td { padding: 0.4rem 0.6rem; border-bottom: 1px solid #e9ecef; }
    .coverage-detail-table .label { color: #495057; font-weight: 500; }
    .coverage-detail-table .value { text-align: right; font-weight: 600; color: #212529; }
</style>
""", unsafe_allow_html=True)



# ==============================================================================
# データ読み込み

# ==============================================================================

persona_data = load_persona_data()
persona_indices = persona_data.index.tolist()

contractor_name_col = persona_data.columns[1] if len(persona_data.columns) > 1 else persona_data.columns[0]
persona_names = persona_data[contractor_name_col].tolist()



# ==============================================================================
# 選択されたペルソナの情報を取得

# ==============================================================================

selected_idx = st.session_state.selected_persona_idx
persona_no = persona_indices[selected_idx]

try:
    persona_info: PersonaInfo = st.session_state.persona_info
except Exception as e:
    st.error(f"ペルソナ情報の取得に失敗しました: {e}")
    st.stop()

current_row = persona_data.loc[persona_no]
customer_category = current_row.iloc[0]
contractor_name = current_row.iloc[1]
gender = current_row.iloc[2]
birth_date = current_row.iloc[4]
has_spouse = current_row.iloc[12]
num_children = current_row.iloc[20]

num_children_int = int(num_children) if pd.notna(num_children) else 0
family_count = 1

spouse_positive = ['有', 'あり', '1', 'true', 'yes', 'あ', '○', '〇']
if pd.notna(has_spouse) and str(has_spouse).lower().strip() in spouse_positive:
    family_count += 1
    spouse_display = "有"
else:
    spouse_display = "無"

family_count += num_children_int

if pd.notna(birth_date):
    if isinstance(birth_date, pd.Timestamp):
        birth_date_str = birth_date.strftime('%Y年%m月%d日')
    else:
        birth_date_str = str(birth_date)
else:
    birth_date_str = "未設定"

# 年齢を計算 #20240409
age = calculate_age(birth_date)  #20240409



# ===========================================
# サイドバー

# ===========================================

with st.sidebar:
    if st.button("🗑️ チャット履歴をクリア", key="clear_chat_btn", use_container_width=True):
        reset_conversation_state()
        st.rerun()
    
    st.markdown('<div class="sidebar-header">ペルソナ選択</div>', unsafe_allow_html=True)
    
    for idx, name in enumerate(persona_names):
        button_type = "primary" if idx == st.session_state.selected_persona_idx else "secondary"
        
        # 各ペルソナの性別と年齢を取得 #20240409
        p_persona_no = persona_indices[idx]  #20240409
        p_row = persona_data.loc[p_persona_no]  #20240409
        p_gender = p_row.iloc[2]  #20240409
        p_birth_date = p_row.iloc[4]  #20240409
        p_age = calculate_age(p_birth_date)  #20240409
        button_text = f"{name}・{p_gender}・{p_age}才"  #20240409
        
        if st.button(button_text, key=f"persona_{idx}", use_container_width=True, type=button_type):  #20240409
            if idx != st.session_state.selected_persona_idx:
                change_persona(idx, persona_data)
                st.rerun()
    
    st.markdown('<div class="sidebar-header">ペルソナ情報</div>', unsafe_allow_html=True)
    
    st.markdown(f"""
    <div class="info-card"><table>
    <tr><td class="label">契約者名</td><td class="value">{contractor_name}</td></tr>
    <tr><td class="label">性別</td><td class="value">{gender}</td></tr>
    <tr><td class="label">生年月日</td><td class="value">{birth_date_str}({age}才)</td></tr>
    <tr><td class="label">配偶者</td><td class="value">{spouse_display}</td></tr>
    <tr><td class="label">子供人数</td><td class="value">{num_children_int}人</td></tr>
    <tr class="highlight-row"><td class="label">家族人数（計）</td><td class="value highlight-value">{family_count}人</td></tr>
    </table></div>
    """, unsafe_allow_html=True)  #20240409
    st.divider()
    
    if st.button("📝 ドラフトプラン作成", key="create_draft_plan_btn", use_container_width=True, type="primary"):
        st.session_state.messages.append({"role": "user", "content": ""})
        st.session_state.button_options = []
        st.session_state.pending_input_display = ""  #20240409 ドラフトプラン作成時は入力欄をクリア
        
        with st.spinner("ドラフトプラン作成中..."):
            try:
                if st.session_state.status_flg in (StatusFlg.PROPOSAL, "PROPOSAL", "StatusFlg.PROPOSAL", "proposal"):
                    explanation_ply = generate_ply_proposal()
                    st.session_state.messages.append({"role": "assistant", "content": explanation_ply})
                    st.session_state.status_flg = ""
                    st.session_state.ply_shown = True
                else:
                    ai_response = call_chat_api("")
                    st.session_state.messages.append({"role": "assistant", "content": ai_response})
                
                # catalog から実際の保障額を同期
                sync_coverage_dict_from_catalog()
                
            except Exception as e:
                st.session_state.messages.append({"role": "assistant", "content": f"エラーが発生しました: {str(e)}"})
        
        st.rerun()



# ===========================================
# メインエリアのレイアウト

# ===========================================

col_chat, col_right = st.columns([3, 1])



# ===========================================
# 右側エリア（レーダーチャート + 保障額表示）

# ===========================================

with col_right:
    st.subheader("必要保障額")
    
    # プラン選択ボタン
    plan_col1, plan_col2, plan_col3 = st.columns(3)
    
    with plan_col1:
        matsu_type = "primary" if st.session_state.selected_radar_plan == "松" else "secondary"
        if st.button("🥇 松", key="radar_plan_matsu", use_container_width=True, type=matsu_type):
            st.session_state.selected_radar_plan = "松"
            st.rerun()
    
    with plan_col2:
        take_type = "primary" if st.session_state.selected_radar_plan == "竹" else "secondary"
        if st.button("🥈 竹", key="radar_plan_take", use_container_width=True, type=take_type):
            st.session_state.selected_radar_plan = "竹"
            st.rerun()
    
    with plan_col3:
        ume_type = "primary" if st.session_state.selected_radar_plan == "梅" else "secondary"
        if st.button("🥉 梅", key="radar_plan_ume", use_container_width=True, type=ume_type):
            st.session_state.selected_radar_plan = "梅"
            st.rerun()
    
    st.caption(f"選択中: **{st.session_state.selected_radar_plan}プラン**")
    
    # レーダーチャートを表示
    radar_fig = create_coverage_radar_chart(st.session_state.selected_radar_plan)
    st.plotly_chart(radar_fig, use_container_width=True)
    
    # 保障額詳細を表示（読み取り専用）
    coverage_data = get_coverage_data_with_categories(st.session_state.selected_radar_plan)
    
    if coverage_data:
        with st.expander("📊 保障額詳細", expanded=False):
            st.markdown(f"**{st.session_state.selected_radar_plan}プランの保障額**")
            
            # テーブル形式で表示
            table_html = '<table class="coverage-detail-table">'
            for category, label, amount in coverage_data:
                amount_man = int(amount / 10000) if amount else 0
                table_html += f'<tr><td class="label">{label}</td><td class="value">{amount_man:,}万円</td></tr>'
            table_html += '</table>'
            
            st.markdown(table_html, unsafe_allow_html=True)
    else:
        st.info("ドラフトプランを作成すると保障額が表示されます")
    
    # 特約保険料確認ボタン
    st.markdown("")
    has_catalog = st.session_state.catalog is not None
    
    if has_catalog:
        if st.button("📋 特約保険料金額確認", key="special_contract_btn", use_container_width=True, type="secondary"):
            show_special_contract_premium_dialog()
    else:
        st.button("📋 特約保険料金額確認", key="special_contract_btn_disabled", use_container_width=True, disabled=True, help="ドラフトプランを作成すると利用可能になります")



# ===========================================
# チャットエリア

# ===========================================

with col_chat:
    st.title("AI チャットアシスタント")
    st.caption(f"現在のペルソナ: **{persona_names[selected_idx]}**（{gender}-{age}才）")  #20240409 性別と年齢を追加
    
    # 高さを指定してスクロール可能なチャットコンテナに変更 #20260410
    # ここで高さを指定すると、この枠の中だけがスクロールするようになります
    chat_container = st.container(height=700)  #20260410 チャット専用のスクロール領域
    
    with chat_container:
        # 最後のユーザーメッセージのインデックスを特定する #20260410
        last_user_idx = -1  #20260410
        for i, msg in enumerate(st.session_state.messages):  #20260410
            if msg["role"] == "user":  #20260410
                last_user_idx = i  #20260410

        for i, message in enumerate(st.session_state.messages):
            with st.chat_message(message["role"]):
                # 最後のユーザーメッセージの直前にHTMLアンカー（目印）を埋め込む #20260410
                if i == last_user_idx:  #20260410
                    st.markdown('<div id="latest-user-message"></div>', unsafe_allow_html=True)  #20260410
                
                if message["content"] == "":
                    st.markdown("*（ドラフトプラン作成）*")
                else:
                    st.markdown(message["content"])
        
        status = st.session_state.status_flg
        
        if st.session_state.button_options and not st.session_state.get("pending_ai_request"):  #20260410
            st.markdown("---")
            st.markdown("**以下から選択してください：**")
            
            for idx, option in enumerate(st.session_state.button_options):
                # コールバック関数を使って状態を更新し、即座にボタンを消す #20260410
                st.button(option, key=f"button_option_{idx}", use_container_width=True, on_click=handle_option_click, args=(option,))  #20260410
        
        elif (status in (StatusFlg.OPTIONS, "OPTIONS", "StatusFlg.OPTIONS", "options")
              and not st.session_state.button_options
              and not st.session_state.ply_shown
              and not st.session_state.get("pending_ai_request")):  #20260410 AIリクエスト待機中は表示しない
            st.markdown("---")
            st.markdown("**AIにどのようなことを尋ねますか？**")
            
            option_buttons = [
                ("1", "プランについて説明してください"),
                ("2", "保障を手厚くする方針でプランを修正してください"),
                ("3", "保険料を下げる方針でプランを修正してください"),
                ("4", "お客さまへ向けた提案文章を作成してください"),
                ("5", "保障内容について教えてください")
            ]
            
            for num, text in option_buttons:
                # コールバック関数を使って状態を更新し、即座にボタンを消す #20260410
                st.button(text, key=f"option_{num}", use_container_width=True, on_click=handle_option_click, args=(text,))  #20260410
        
        elif (status in (StatusFlg.PROPOSAL, "PROPOSAL", "StatusFlg.PROPOSAL", "proposal")
              and not st.session_state.get("pending_ai_request")):  #20260410 AIリクエスト待機中は表示しない
            st.markdown("---")
            st.markdown("**プランを選択してください**")
            
            col_matsu, col_take, col_ume = st.columns(3)
            
            with col_matsu:
                if st.button("🥇 松", key="plan_matsu", use_container_width=True):
                    st.session_state.messages.append({"role": "user", "content": "松プランを選択します"})
                    st.session_state.selected_radar_plan = "松"
                    st.session_state.pending_input_display = "松プランを選択します"  #20240409 選択した内容を入力欄に表示
                    
                    with st.spinner("People Like You 分析中..."):
                        try:
                            result_text = generate_ply_proposal(PlanType.MATSU)
                            st.session_state.messages.append({"role": "assistant", "content": result_text})
                            st.session_state.status_flg = ""
                            st.session_state.ply_shown = True
                            # catalog から実際の保障額を同期
                            sync_coverage_dict_from_catalog()
                        except Exception as e:
                            st.session_state.messages.append({"role": "assistant", "content": f"エラーが発生しました: {str(e)}"})
                    
                    st.rerun()
            
            with col_take:
                if st.button("🥈 竹", key="plan_take", use_container_width=True):
                    st.session_state.messages.append({"role": "user", "content": "竹プランを選択します"})
                    st.session_state.selected_radar_plan = "竹"
                    st.session_state.pending_input_display = "竹プランを選択します"  #20240409 選択した内容を入力欄に表示
                    
                    with st.spinner("People Like You 分析中..."):
                        try:
                            result_text = generate_ply_proposal(PlanType.TAKE)
                            st.session_state.messages.append({"role": "assistant", "content": result_text})
                            st.session_state.status_flg = ""
                            st.session_state.ply_shown = True
                            # catalog から実際の保障額を同期
                            sync_coverage_dict_from_catalog()
                        except Exception as e:
                            st.session_state.messages.append({"role": "assistant", "content": f"エラーが発生しました: {str(e)}"})
                    
                    st.rerun()
            
            with col_ume:
                if st.button("🥉 梅", key="plan_ume", use_container_width=True):
                    st.session_state.messages.append({"role": "user", "content": "梅プランを選択します"})
                    st.session_state.selected_radar_plan = "梅"
                    st.session_state.pending_input_display = "梅プランを選択します"  #20240409 選択した内容を入力欄に表示
                    
                    with st.spinner("People Like You 分析中..."):
                        try:
                            result_text = generate_ply_proposal(PlanType.UME)
                            st.session_state.messages.append({"role": "assistant", "content": result_text})
                            st.session_state.status_flg = ""
                            st.session_state.ply_shown = True
                            # catalog から実際の保障額を同期
                            sync_coverage_dict_from_catalog()
                        except Exception as e:
                            st.session_state.messages.append({"role": "assistant", "content": f"エラーが発生しました: {str(e)}"})
                    
                    st.rerun()
    
    # 常に画面下部に固定される公式チャット入力コンポーネントに変更 #20260410
    if prompt := st.chat_input("メッセージを入力してください..."):  #20260410 入力欄を最下部に固定
        st.session_state.messages.append({"role": "user", "content": prompt})  #20260410 ユーザーメッセージを追加
        st.session_state.button_options = []  #20260410 選択肢をクリア
        st.session_state.pending_input_display = ""  #20260410 古い入力表示をクリア
        st.session_state.pending_ai_request = prompt  #20260410 AIリクエストのフラグを立てる
        st.rerun()  #20260410 画面を再描画してメッセージを即反映

    # ==============================================================================
    # 遅延実行されるAIリクエストの処理 #20260410
    # ==============================================================================
    if st.session_state.get("pending_ai_request"):  #20260410
        request_text = st.session_state.pending_ai_request  #20260410
        st.session_state.pending_ai_request = None  #20260410 フラグをクリア
        
        with st.chat_message("assistant"):  #20260410 スピナーをチャット枠内に表示
            with st.spinner("考え中..."):  #20260410
                try:  #20260410
                    # プラン選択の場合の特殊処理 #20260410
                    if request_text.startswith("PLAN_"):  #20260410
                        plan_name = request_text.replace("PLAN_", "")  #20260410
                        plan_enum = PlanType.MATSU if plan_name == "松" else (PlanType.TAKE if plan_name == "竹" else PlanType.UME)  #20260410
                        result_text = generate_ply_proposal(plan_enum)  #20260410
                        st.session_state.messages.append({"role": "assistant", "content": result_text})  #20260410
                        st.session_state.status_flg = ""  #20260410
                        st.session_state.ply_shown = True  #20260410
                    # 通常の提案やチャットの場合 #20260410
                    elif st.session_state.status_flg in (StatusFlg.PROPOSAL, "PROPOSAL", "StatusFlg.PROPOSAL", "proposal"):  #20260410
                        explanation_ply = generate_ply_proposal()  #20260410
                        st.session_state.messages.append({"role": "assistant", "content": explanation_ply})  #20260410
                        st.session_state.status_flg = ""  #20260410
                        st.session_state.ply_shown = True  #20260410
                    else:  #20260410
                        ai_response = call_chat_api(request_text)  #20260410
                        st.session_state.messages.append({"role": "assistant", "content": ai_response})  #20260410
                    
                    sync_coverage_dict_from_catalog()  #20260410
                    
                except Exception as e:  #20260410
                    st.session_state.messages.append({"role": "assistant", "content": f"エラーが発生しました: {str(e)}"})  #20260410
        
        st.session_state.should_scroll_to_user = True  #20260410 回答が終わったらスクロールするようにフラグを立てる
        st.rerun()  #20260410 処理完了後に画面を最終更新


st.markdown("""
<style>
    [data-testid="stSidebarResizer"]{ width: 1px !important; background: #d0d7de !important; }
    /* #20260410 開閉ボタンの非表示設定を削除し、トグル可能に戻す */
    section[data-testid="stMain"]{ padding-left: 0.5rem !important; overflow: hidden !important; height: 100vh !important; }  #20260410 メインエリアを固定
    section[data-testid="stMain"] .block-container{ padding-left: 0.5rem !important; height: 100vh !important; overflow: hidden !important; padding-top: 1rem !important; max-width: 100% !important; } #20260410 内部も固定し余白調整
    [data-testid="stMainBlockContainer"] { padding-top: 1rem !important; } /* Streamlitの新バージョン用 */
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# AI回答後の自動スクロール（ハック） #20260410
# ==============================================================================
if st.session_state.get("should_scroll_to_user"):  #20260410 スクロールフラグが立っている場合のみ実行
    components.html(
        """
        <script>
            // Streamlitの親フレーム（実際のページ）からアンカーを探す #20260410
            const element = window.parent.document.getElementById("latest-user-message");
            if (element) {
                // Streamlitのデフォルトの自動スクロール（一番下へ）と競合しないよう、少し遅延させる #20260410
                setTimeout(() => {
                    element.scrollIntoView({behavior: "smooth", block: "start"});
                }, 300);
            }
        </script>
        """,
        height=0  #20260410 iframeを見えなくする
    )
    st.session_state.should_scroll_to_user = False  #20260410 一度実行したらフラグを戻す
