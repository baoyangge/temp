import streamlit as st
import streamlit.components.v1 as components  #20260410 李修正JavaScript実行用
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import plotly.graph_objects as go
import re
from datetime import datetime, date  #20240409
import math
import time

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
#from my10_generate_people_like_you_talk import GeneratePeopleLikeYouTalk

#修正_20260409_岡田
from enum import Enum

class WorkflowStage(Enum):
    """ワークフローの進行状況を管理するEnum"""
    START = "start"                    # 開始（初期状態）
    PLAN_CREATED = "plan_created"      # プラン作成完了
    PLAN_MODIFIED = "plan_modified"    # プラン修正中
    PLAN_DETAIL = "plan_detail"        # プラン詳細説明中
    PLAN_PROPOSED = "plan_proposed"    # プラン提案中
    END = "end"                        # 完了


# ★ ヘルパー関数を追加：ステージの value を安全に取得する
def get_stage_value(stage) -> str:
    """ステージの value を安全に取得する"""
    if isinstance(stage, WorkflowStage):
        return stage.value
    return str(stage)
#修正_20260409_岡田


# ==============================================================================
# ボタンクリック時のコールバック関数 #20260410
# ==============================================================================
def handle_option_click(option_text: str, workflow_action: str = None):  #20260410 #修正_20260409_岡田
    """オプションボタンがクリックされた時の処理"""  #20260410 李修正　
    #修正_20260409_岡田
    # ワークフロー更新
    if workflow_action:
        update_workflow_stage(workflow_action)
    #修正_20260409_岡田
    st.session_state.messages.append({"role": "user", "content": option_text})  #20260410 李修正　
    st.session_state.button_options = []  #20260410 李修正　選択肢を即座に消す
    st.session_state.pending_input_display = ""  #20260410 李修正　入力欄もクリア
    st.session_state.pending_ai_request = option_text  #20260410 李修正　後続の処理でAIを呼ぶフラグを立てる
    st.session_state.should_scroll_to_user = False  #20260410 李修正　新しいリクエストが来たのでスクロールフラグをリセット
    # ★ 処理中フラグを設定
    st.session_state.is_processing = True
    st.session_state.processing_message = get_spinner_text(option_text)

def handle_plan_click(plan_name: str):  #20260410 李修正　
    """プラン選択ボタンがクリックされた時の処理"""  #20260410 李修正　
    st.session_state.messages.append({"role": "user", "content": f"{plan_name}プランを選択します"})  #20260410 李修正　
    st.session_state.selected_radar_plan = plan_name  #20260410 李修正　
    st.session_state.pending_input_display = ""  #20260410 李修正　
    st.session_state.pending_ai_request = f"PLAN_{plan_name}"  #20260410 李修正　プラン選択専用のフラグ
    st.session_state.should_scroll_to_user = False  #20260410 李修正　新しいリクエストが来たのでスクロールフラグをリセット
    # ★ 処理中フラグを設定
    st.session_state.is_processing = True
    st.session_state.processing_message = get_spinner_text(f"{plan_name}プランを選択します")

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

PLAN_TYPE_TO_COVERAGE_LEVEL = {
    PlanType.MATSU: CoverageLevel.ENHANCED,
    PlanType.TAKE: CoverageLevel.STANDARD,
    PlanType.UME: CoverageLevel.BASIC,
}

#修正_20260414_岡田
SPECIAL_CONTRACT_TO_COVERAGE_CATEGORY = {
    "injury_illness_special_contracts": "ケガ・入院",
    "cancer_special_contracts": "がん",
    "circulatory_special_contracts": "循環器",
    "severe_disease_special_contracts": "特定重度疾病",
    "disability_special_contracts": "就業不能",
    "health_promotion_special_contracts": "健康増進",
    "death_special_contracts": "万一",
}
#修正_20260414_岡田

RADAR_LABEL_COLOR_MAP = {
    "万一": "#069EDB",
    "特定重度疾病": "#F37932",
    "健康増進": "#00A78E",
    "がん": "#F05891",
    "循環器": "#6C67AE",
    "就業不能": "#6FBF54",
}
#修正_20260415岡田さん

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
# ステージの順序を定義（グローバル）
# ==============================================================================

STAGE_ORDER = {
    WorkflowStage.START.value: 0,
    WorkflowStage.PLAN_CREATED.value: 1,
    WorkflowStage.PLAN_MODIFIED.value: 2,
    WorkflowStage.PLAN_DETAIL.value: 3,
    WorkflowStage.PLAN_PROPOSED.value: 4,
    WorkflowStage.END.value: 5,
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
            options.append(f"{option}")
    
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

    #修正_20260414_岡田
    # 保障額（特約のbenefit_amount_yenを合算）
    if "coverage_amount_dict" not in st.session_state:
        st.session_state.coverage_amount_dict = {}

    # ドラフトプラン作成時の必要保障額（最大値計算用に固定）
    if "initial_required_coverage_dict" not in st.session_state:
        st.session_state.initial_required_coverage_dict = {}
    #修正_20260414_岡田

    # 選択肢から選択された内容を表示するための変数 #20240409
    if "pending_input_display" not in st.session_state:  #20240409
        st.session_state.pending_input_display = ""  #20240409

    # AIへのリクエストを遅延実行するための状態変数 #20260410 李修正　
    if "pending_ai_request" not in st.session_state:  #20260410 李修正　
        st.session_state.pending_ai_request = None  #20260410 李修正　
    st.session_state.should_scroll_to_user = False  #20260410 李修正　
    
    # 自動スクロール用のフラグ #20260410 李修正　
    if "should_scroll_to_user" not in st.session_state:  #20260410 李修正　
        st.session_state.should_scroll_to_user = False  #20260410 李修正　

    # ★ 処理中状態を管理するフラグ
    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
    
    # ★ 処理中に表示するメッセージ
    if "processing_message" not in st.session_state:
        st.session_state.processing_message = ""

    #修正_20260409_岡田
    # ★ ワークフローの進行状況を文字列（value）で管理するように変更
    if "workflow_stage" not in st.session_state:
        st.session_state.workflow_stage = WorkflowStage.START.value  # ← 文字列で保存
    
    # 各ステージが実行されたかどうかを追跡するフラグ
    if "detail_executed" not in st.session_state:
        st.session_state.detail_executed = False
    
    if "modified_executed" not in st.session_state:
        st.session_state.modified_executed = False
    
    if "proposed_executed" not in st.session_state:
        st.session_state.proposed_executed = False
    #修正_20260409_岡田


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
    #修正_20260414_岡田
    st.session_state.coverage_amount_dict = {}
    st.session_state.initial_required_coverage_dict = {}
    #修正_20260414_岡田
    st.session_state.pending_input_display = ""  
    #20240409
    st.session_state.pending_ai_request = None  #20260410 李修正　
    st.session_state.should_scroll_to_user = False  #20260410 李修正　
    # ★ 処理中状態をリセット
    st.session_state.is_processing = False
    st.session_state.processing_message = ""
    #修正_20260409_岡田
    # ★ ワークフロー進行状況をリセット（文字列で保存）
    st.session_state.workflow_stage = WorkflowStage.START.value
    st.session_state.detail_executed = False
    st.session_state.modified_executed = False
    st.session_state.proposed_executed = False
    #修正_20260409_岡田


#修正_20260409_岡田
# ==============================================================================
# ワークフロー進行状況の更新関数
# ==============================================================================

def update_workflow_stage(action: str) -> None:
    """
    ワークフローの進行状況を更新する
    
    Args:
        action: 実行するアクション
            - "plan_create": プラン作成完了
            - "plan_detail_start": プラン詳細説明開始
            - "plan_detail_end": プラン詳細説明終了（ステージは維持）
            - "plan_modify_start": プラン修正開始
            - "plan_modify_end": プラン修正終了（ステージは維持）
            - "plan_propose_start": プラン提案開始
            - "end": 完了
    """
    if action == "plan_create":
        st.session_state.workflow_stage = WorkflowStage.PLAN_CREATED.value
    
    elif action == "plan_detail_start":
        st.session_state.workflow_stage = WorkflowStage.PLAN_DETAIL.value
    
    elif action == "plan_detail_end":
        # ★ ステージは変更しない（現在のステージを維持）
        st.session_state.detail_executed = True
    
    elif action == "plan_modify_start":
        st.session_state.workflow_stage = WorkflowStage.PLAN_MODIFIED.value
    
    elif action == "plan_modify_end":
        # ★ ステージは変更しない（現在のステージを維持）
        st.session_state.modified_executed = True
    
    elif action == "plan_propose_start":
        st.session_state.workflow_stage = WorkflowStage.PLAN_PROPOSED.value
    
    elif action == "end":
        st.session_state.proposed_executed = True
        st.session_state.workflow_stage = WorkflowStage.END.value
#修正_20260409_岡田


#修正_20260409_岡田
# ==============================================================================
# spinner文言決定関数
# ==============================================================================

def get_spinner_text(user_text: str) -> str:
    """
    ユーザー入力またはボタン文言から適切なspinner文言を返す
   
    Args:
        user_text: ユーザーが入力したテキストまたはボタン文言
   
    Returns:
        表示するspinner文言
    """
    if not user_text:
        return "内容を整理しています"
   
    text = user_text.strip()
   
    # 優先度1: 固定ボタン文言の完全一致
    button_text_mapping = {
        "「プラン説明」カテゴリーについて詳しく説明してください": "説明する内容を考えています",
        "「プラン修正」保障を手厚くする方針で修正してください": "保障を手厚くする内容を検討中です",
        "「プラン修正」保険料を下げる方針で修正してください": "保険料を下げる案を検討中です",
        "「提案文作成」お客さま向けの提案文を作成してください": "提案文を作成中です...約1.5分かかりますので、少々お待ちください",
        "「プラン説明」プランの保障内容について詳しく説明ください": "保障内容を確認中です",
    }
   
    if text in button_text_mapping:
        return button_text_mapping[text]
   
    # 優先度2: キーワード判定（順番に判定、最初にマッチしたものを返す）
   
    # 「保険料」かつ「下げ/安く/削減」
    if "保険料" in text and any(kw in text for kw in ["下げ", "安く", "削減"]):
        return "保険料を下げる案を検討中です"
   
    # 「手厚く/増やす/上げ」
    if any(kw in text for kw in ["手厚く", "増やす", "上げ"]):
        return "保障を手厚くする内容を検討中です"
   
    # 「提案/文章」
    if any(kw in text for kw in ["提案", "文章"]):
        return "提案文を作成中です。約1分間かかりますので、少々お待ちください。"
   
    # 「説明/教えて」
    if any(kw in text for kw in ["説明", "教えて"]):
        return "説明する内容を考えています"
   
    # ★「修正」キーワード判定を削除
    # 「プランを修正しています」はワークフローステージからのみ出力
   
    # 優先度3: workflow_stage から推定
    current_stage_value = st.session_state.workflow_stage
    if isinstance(current_stage_value, WorkflowStage):
        current_stage_value = current_stage_value.value
   
    stage_text_mapping = {
        WorkflowStage.PLAN_DETAIL.value: "説明する内容を考えています",
        WorkflowStage.PLAN_MODIFIED.value: "プランを修正しています",  # ★保障額変更時のみここで出力
        WorkflowStage.PLAN_PROPOSED.value: "提案文を作成中です。約1.5分かかりますので、少々お待ちください。",
    }
   
    if current_stage_value in stage_text_mapping:
        return stage_text_mapping[current_stage_value]
   
    # 優先度4: デフォルト
    return "内容を整理しています"
#修正_20260409_岡田


#修正_20260409_岡田
def get_workflow_progress_html() -> str:
    """
    ワークフローの進行状況を表すHTMLを生成する
    ★ 固定ヘッダーとして表示するためのHTML生成関数
    """
    # ★ セッション状態から文字列として取得
    current_stage_value = st.session_state.workflow_stage
    
    # 念のため、Enumオブジェクトの場合は value を取得
    if isinstance(current_stage_value, WorkflowStage):
        current_stage_value = current_stage_value.value
    
    # ★ 順序: プラン修正 → プラン詳細説明
    stages = [
        ("ペルソナ選択", WorkflowStage.START.value),
        ("プラン作成", WorkflowStage.PLAN_CREATED.value),
        ("プラン修正", WorkflowStage.PLAN_MODIFIED.value),
        ("プラン説明", WorkflowStage.PLAN_DETAIL.value),
        ("プラン提案", WorkflowStage.PLAN_PROPOSED.value),
        #mark0414li("END", WorkflowStage.END.value),
    ]
    
    stage_items = []
    
    for i, (label, stage_value) in enumerate(stages):
        # ★ 文字列で比較
        if stage_value == current_stage_value:
            # 現在のステージ：ハイライト（緑）
            bg_color = "#29A383"
            text_color = "#ffffff"
            border_color = "#29A383"
        else:
            # その他のステージ：グレー
            bg_color = "#f8f9fa"
            text_color = "#6c757d"
            border_color = "#dee2e6"
        
        # ★ 矢印の色を #FABF00 に変更（現在ステージの手前まで黄色、それ以降はグレー）
        current_order = STAGE_ORDER.get(current_stage_value, 0)
        stage_order = STAGE_ORDER.get(stage_value, 0)
        arrow_color = "#FABF00" if stage_order < current_order else "#dee2e6"
        
        # 最後のステージ以外は矢印を追加
        arrow = f'<span style="margin:0 8px;color:{arrow_color};font-size:1.2rem;">▶</span>' if i < len(stages) - 1 else ''
        
        # ステージのHTML（アイコンなし、ラベルのみ）
        stage_items.append(
            f'<span style="display:inline-flex;align-items:center;background:{bg_color};'
            f'color:{text_color};border:2px solid {border_color};border-radius:8px;'
            f'padding:6px 14px;font-size:16px;font-weight:600;">{label}</span>{arrow}'
        )

    
    return "".join(stage_items)


def render_workflow_progress_header() -> None:
    """
    ワークフローの進行状況を固定ヘッダーとして表示する
    ★ st.markdown を使用して固定ヘッダーとして実装
    ★ 下線を削除
    """
    workflow_html = get_workflow_progress_html()
    
    # 固定ヘッダー用のHTML/CSS（下線なし）
    st.markdown(f"""
    <div class="workflow-header">
        <div class="workflow-container">
            {workflow_html}
        </div>
    </div>
    """, unsafe_allow_html=True)
#修正_20260409_岡田


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



    
#20260415岡田修正
# ==============================================================================
# catalog変更検知関数（修正版：特約レベルの変更も検知）
# ==============================================================================

def get_catalog_id(catalog) -> Optional[str]:
    """
    catalogの識別子を生成する。
    catalogの内容が変わったら異なるIDを返す。
    ★ 特約レベルの benefit_amount_yen, premium_yen, benefit_amount_yen_for_kitei_check を含める
    """
    if catalog is None:
        return None
    
    try:
        id_parts = []
        
        # 特約カテゴリの属性名リスト
        special_contract_attrs = [
            "cancer_special_contracts",
            "health_promotion_special_contracts",
            "disability_special_contracts",
            "circulatory_special_contracts",
            "severe_disease_special_contracts",
            "injury_illness_special_contracts",
        ]
        
        for plan_type in [PlanType.MATSU, PlanType.TAKE, PlanType.UME]:
            plan = catalog.get(plan_type)
            if not plan:
                continue
            
            plan_name = plan_type.value if hasattr(plan_type, 'value') else str(plan_type)
            
            # total_premium があれば使用
            if hasattr(plan, 'total_premium') and plan.total_premium is not None:
                id_parts.append(f"{plan_name}:total:{plan.total_premium}")
            
            # 各特約カテゴリを確認
            for attr_name in special_contract_attrs:
                contracts = getattr(plan, attr_name, None)
                if not contracts or not isinstance(contracts, dict):
                    continue
                
                for contract_type, contract_info in contracts.items():
                    if contract_info is None:
                        continue
                    
                    ct_name = contract_type.value if hasattr(contract_type, 'value') else str(contract_type)
                    
                    # ★ 3つの値すべてを識別子に含める
                    benefit = getattr(contract_info, 'benefit_amount_yen', 0) or 0
                    premium = getattr(contract_info, 'premium_yen', 0) or 0
                    kitei = getattr(contract_info, 'benefit_amount_yen_for_kitei_check', 0) or 0
                    
                    id_parts.append(f"{plan_name}:{ct_name}:b{benefit}:p{premium}:k{kitei}")
        
        if id_parts:
            return "|".join(id_parts)
        
        # フォールバック：オブジェクトのidを使用
        return str(id(catalog))
    
    except Exception as e:
        add_debug_log(f"get_catalog_id error: {e}")
        return str(id(catalog))

def is_catalog_changed(new_catalog) -> bool:
    """
    catalogが前回から変更されたかどうかを判定する。
    """
    new_id = get_catalog_id(new_catalog)
    previous_id = st.session_state.get("previous_catalog_id")
    
    add_debug_log(f"is_catalog_changed: new_id length={len(new_id) if new_id else 0}")
    add_debug_log(f"is_catalog_changed: previous_id length={len(previous_id) if previous_id else 0}")
    add_debug_log(f"is_catalog_changed: changed={new_id != previous_id}")
    
    # 前回がNoneで今回も有効なcatalogがない場合は変更なし
    if previous_id is None and new_id is None:
        return False
    
    # 前回がNoneで今回は有効なcatalogがある場合は変更あり
    if previous_id is None and new_id is not None:
        return True
    
    # IDが異なれば変更あり
    return new_id != previous_id


def update_catalog_id(catalog) -> None:
    """
    catalogの識別子を更新する。
    """
    st.session_state.previous_catalog_id = get_catalog_id(catalog)
    add_debug_log(f"update_catalog_id: updated (length={len(st.session_state.previous_catalog_id) if st.session_state.previous_catalog_id else 0})")
#20260415岡田修正

# ==============================================================================
# catalogから保障額を計算する関数（デバッグ情報付き）
# ==============================================================================


#20260415岡田
def calculate_coverage_amount_from_catalog() -> Dict:
    """
    catalogの各特約のbenefit_amount_yenを合算して保障額を計算する
    ★ カテゴリ名の部分一致も考慮
    
    Returns:
        各CoverageLevelごとのカテゴリ別保障額の辞書
    """
    catalog = st.session_state.catalog
    if not catalog:
        add_debug_log("calculate_coverage: catalog is None")
        return {}
    
    result = {}
    
    for plan_type, coverage_level in PLAN_TYPE_TO_COVERAGE_LEVEL.items():
        plan = catalog.get(plan_type)
        if not plan:
            continue
        
        # 必要保障額のカテゴリを基準に保障額を計算
        required_coverage = st.session_state.required_coverage_amount_dict.get(coverage_level, {})
        
        # カテゴリ名とカテゴリオブジェクトのマッピングを作成
        category_name_to_obj = {
            (category.value if hasattr(category, 'value') else str(category)): category
            for category in required_coverage.keys()
        }
        
        category_totals = {cat: 0 for cat in required_coverage.keys()}
        
        # 各特約カテゴリから保障額を合算
        for attr_name, coverage_category_name in SPECIAL_CONTRACT_TO_COVERAGE_CATEGORY.items():
            contracts = getattr(plan, attr_name, None)
            
            if not contracts:
                continue
            
            # カテゴリオブジェクトを検索（完全一致または部分一致）
            target_category = category_name_to_obj.get(coverage_category_name)
            
            if not target_category:
                for cat_name, cat_obj in category_name_to_obj.items():
                    if coverage_category_name in cat_name or cat_name in coverage_category_name:
                        target_category = cat_obj
                        break
            
            if not target_category:
                continue
            
            if isinstance(contracts, dict):
                for contract_type, contract_info in contracts.items():
                    if contract_info is None:
                        continue
                    
                    # benefit_amount_yen の取得
                    benefit_amount = 0
                    if hasattr(contract_info, 'benefit_amount_yen'):
                        benefit_amount = contract_info.benefit_amount_yen or 0
                    elif isinstance(contract_info, dict) and 'benefit_amount_yen' in contract_info:
                        benefit_amount = contract_info.get('benefit_amount_yen', 0) or 0
                    
                    category_totals[target_category] += benefit_amount
        
        result[coverage_level] = category_totals
    
    return result
#20260415岡田




# ==============================================================================
# catalog から保障額を同期する関数

# ==============================================================================
#修正_20260414_岡田
def sync_coverage_dict_from_catalog() -> None:
    """
    catalog の Plan.coverage_amount_by_category があれば、
    required_coverage_amount_dict を catalog の値で同期（上書き）する。
    また、初回のみレーダーチャートに表示する項目を決定し、
    初回の必要保障額を最大値計算用に保存する。
    さらに、保障額も計算して同期する。
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
    
    # 初回のみ最大値計算用の必要保障額を保存
    if not st.session_state.initial_required_coverage_dict and updated_dict:
        st.session_state.initial_required_coverage_dict = {
            level: dict(data) for level, data in updated_dict.items()
        }
    
    # 保障額を計算して同期
    st.session_state.coverage_amount_dict = calculate_coverage_amount_from_catalog()
#修正_20260414_岡田



# ==============================================================================
# レーダーチャート作成関数

# ==============================================================================

# 20260416岡田修正
def create_coverage_radar_chart(plan_name: str) -> go.Figure:
    """
    必要保障額と保障額の2系列を表示するレーダーチャートを作成
    - 凡例：左上
    - ラベル：カスタムアノテーションで表示（項目名は色付き、金額は黒）
    - レーダー本体：できるだけ大きく
    - 必要保障額：薄いグレー（破線）
    - 保障額：プラン色（実線）
    - 100%基準：真円（25%単位でグリッド線を表示）
    """
    
    required_coverage_dict = st.session_state.required_coverage_amount_dict
    coverage_dict = st.session_state.coverage_amount_dict
    visible_categories = st.session_state.radar_visible_categories

    CHART_HEIGHT = 650
    CHART_MARGIN = dict(l=10, r=10, t=10, b=10)

    if not required_coverage_dict:
        fig = go.Figure()
        fig.add_annotation(
            text="データがありません",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=14, color="#666666"),
            align="center"
        )
        fig.update_layout(
            height=CHART_HEIGHT,
            margin=CHART_MARGIN,
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff"
        )
        return fig

    coverage_level = PLAN_TO_COVERAGE_LEVEL.get(plan_name)
    if coverage_level is None or coverage_level not in required_coverage_dict:
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
            height=CHART_HEIGHT,
            margin=CHART_MARGIN,
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff"
        )
        return fig

    required_plan_data = required_coverage_dict[coverage_level]
    coverage_plan_data = coverage_dict.get(coverage_level, {})

    base_labels: List[str] = []
    required_values_yen: List[float] = []
    required_values_man: List[float] = []
    coverage_values_yen: List[float] = []
    coverage_values_man: List[float] = []
    max_values: List[float] = []

    for category, amount in required_plan_data.items():
        if visible_categories is not None and category not in visible_categories:
            continue

        label = category.value if hasattr(category, "value") else str(category)
        base_labels.append(label)

        required_amt = float(amount or 0)
        required_values_yen.append(required_amt)
        required_values_man.append(required_amt / 10000.0)

        coverage_amt = float(coverage_plan_data.get(category, 0) or 0)
        coverage_values_yen.append(coverage_amt)
        coverage_values_man.append(coverage_amt / 10000.0)

        max_amt = required_amt
        max_values.append(max_amt if max_amt > 0 else 1)

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
            height=CHART_HEIGHT,
            margin=CHART_MARGIN,
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff"
        )
        return fig

    normalized_required = [(v / mv) * 100 if mv > 0 else 0 for v, mv in zip(required_values_yen, max_values)]
    normalized_coverage = [(v / mv) * 100 if mv > 0 else 0 for v, mv in zip(coverage_values_yen, max_values)]

    # ★ theta用ラベル（アノテーションで別途表示するため、シンプルなラベルを使用）
    theta_closed = base_labels + [base_labels[0]]
    normalized_required_closed = normalized_required + [normalized_required[0]]
    normalized_coverage_closed = normalized_coverage + [normalized_coverage[0]]

    required_fill_color = "rgba(180, 180, 180, 0.2)"
    required_line_color = "#aaaaaa"
    
    grid_line_color = "rgba(200, 200, 200, 0.5)"

    coverage_colors = {
        "松": {"fill": "rgba(41, 163, 131, 0.4)", "line": "#29A383"},
        "竹": {"fill": "rgba(250, 191, 0, 0.4)", "line": "#FABF00"},
        "梅": {"fill": "rgba(102, 126, 234, 0.4)", "line": "#667eea"},
    }
    coverage_config = coverage_colors.get(plan_name, coverage_colors["松"])

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=normalized_required_closed,
        theta=theta_closed,
        fill="toself",
        fillcolor=required_fill_color,
        line=dict(color=required_line_color, width=2, dash="dash"),
        name="必要保障額",
        hovertemplate="%{theta}<br>充足率: %{r:.1f}%<extra></extra>",
    ))

    fig.add_trace(go.Scatterpolar(
        r=normalized_coverage_closed,
        theta=theta_closed,
        fill="toself",
        fillcolor=coverage_config["fill"],
        line=dict(color=coverage_config["line"], width=2),
        name="保障額",
        hovertemplate="%{theta}<br>充足率: %{r:.1f}%<extra></extra>",
    ))

    # ★ polarチャートのドメイン設定
    domain_x = [0.02, 0.98]
    domain_y = [0.10, 0.98]

    fig.update_layout(
        polar=dict(
            domain=dict(x=domain_x, y=domain_y),
            radialaxis=dict(
                visible=True,
                range=[0, 150],
                tickvals=[25, 50, 75, 100],
                ticktext=["25%", "50%", "75%", "100%"],
                showgrid=True,
                gridcolor=grid_line_color,
                gridwidth=1,
                showticklabels=True,
                tickfont=dict(size=10, color="#888888"),
                showline=False,
            ),
            angularaxis=dict(
                showticklabels=False,  # ★ デフォルトラベルを非表示（アノテーションで表示）
                showgrid=False,
                showline=False,
            ),
            bgcolor="#ffffff",
        ),
        showlegend=True,
        legend=dict(
            orientation="h",
            x=0.01, xanchor="left",
            y=0.99, yanchor="top",
            font=dict(size=14),
            bgcolor="rgba(255,255,255,0.0)",
        ),
        height=CHART_HEIGHT,
        margin=CHART_MARGIN,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
    )

    # ★ カスタムラベルをアノテーションとして追加（項目名は色付き、金額は黒）
    center_x = (domain_x[0] + domain_x[1]) / 2
    center_y = (domain_y[0] + domain_y[1]) / 2
    
    # ラベルを配置する半径係数（チャートの外側に配置）
    label_radius = 0.48
    
    n_categories = len(base_labels)
    for i, (label, req, cov) in enumerate(zip(base_labels, required_values_man, coverage_values_man)):
        # 角度を計算（90度から開始、時計回り）
        angle_deg = 90 - (360 / n_categories) * i
        angle_rad = math.radians(angle_deg)
        
        # ★ ラベルの色を取得（マッピングにない場合はデフォルト色）
        label_color = RADAR_LABEL_COLOR_MAP.get(label, "#333333")
        
        # 位置を計算
        x_pos = center_x + label_radius * math.cos(angle_rad)
        y_pos = center_y + label_radius * math.sin(angle_rad)
        
        # ★ カテゴリ名のアノテーション（色付き、上側）
        fig.add_annotation(
            x=x_pos,
            y=y_pos,
            xref="paper",
            yref="paper",
            text=f"<b>{label}</b>",
            showarrow=False,
            font=dict(size=14, color=label_color),
            align="center",
            yshift=24,
        )
        
        # ★ 金額のアノテーション（現行色：黒、下側）
        fig.add_annotation(
            x=x_pos,
            y=y_pos,
            xref="paper",
            yref="paper",
            text=f"必要:{req:,.0f}万<br>保障:{cov:,.0f}万",
            showarrow=False,
            font=dict(size=12, color="#333333"),
            align="center",
            yshift=-8,
        )

    return fig
# 20260416岡田修正





def get_coverage_data_with_categories(plan_name: str) -> List[Tuple]:
    """
    指定プランの保障額データをカテゴリオブジェクトと共に取得
    松プランで0円の項目は  ィルタリング
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
                elif benefit_amount == -999:
                    benefit_display = "なし"
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
                <div style="font-weight: 600; color: {color}; font-size: 1.3rem;">{plan_name}</div>
                <div style="font-size: 2rem; font-weight: 700; color: #333;">{total:,}円</div>
            </div>
            """, unsafe_allow_html=True)
    
    #radar 3plan 20260410
    radar_cols = st.columns(len(available_plans))
    for i, plan_name in enumerate(available_plans):
        with radar_cols[i]:
            # 「松プラン」→「松」に変換
            short_plan_name = plan_name.replace("プラン", "")
            radar_fig = create_coverage_radar_chart(short_plan_name)
            st.plotly_chart(radar_fig, use_container_width=True)

    st.divider()
    
    st.markdown("### 📋 特約詳細")
    
    ordered_categories = [cat_name for _, cat_name in SPECIAL_CONTRACT_CATEGORY_ORDER]
    
    CATEGORY_BG_COLORS = {
        "病気・ケガへの備え": "#F17079",
        "がん保障": "#F37932",
        "循環器病保障": "#F37932",
        "特定重度疾病保障": "#F37932",
        "障害・就労不能保障": "#6FBF54",
        "健康促進保障": "#00A78E",
    }

    for category in ordered_categories:
        has_category = any(
            category in data[plan_name]["categories"] 
            for plan_name in available_plans 
            if plan_name in data
        )
        
        if not has_category:
            continue
        
        # ★ 20260410：背景色付きのHTMLに変更
        bg_color = CATEGORY_BG_COLORS.get(category, "#f8f9fa")
        st.markdown(f"""
        <div style="background-color: {bg_color}; padding: 8px 12px; border-radius: 4px; margin: 10px 0 5px 0;">
            <span style="font-weight: 600; color: white;">🔹 {category}</span>
        </div>
        """, unsafe_allow_html=True)
        
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
                .sc-table {{ width: 100%; border-collapse: collapse; font-size: 1.5rem; margin-bottom: 1rem; }}
                .sc-table th, .sc-table td {{ border: 1px solid #e9ecef; padding: 10px 12px; vertical-align: middle; }}
                .sc-table thead th {{ background: #f8f9fa; font-weight: 1600; }}
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



    sync_coverage_dict_from_catalog()
    '''
    # ★ catalogが変更された場合のみ、保障額を同期
    if catalog_changed:
        add_debug_log("call_chat_api: catalog changed, syncing coverage dict")
        t7 = time.perf_counter()
        sync_coverage_dict_from_catalog()
        update_catalog_id(catalog)
        t8 = time.perf_counter()
        add_debug_log(f"[T] sync_coverage+update_catalog_id: {(t8 - t7):.3f}s")
    else:
        add_debug_log("call_chat_api: catalog not changed, skip sync")
    '''
    
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
    
    #修正_20260409_岡田
    # ★ 現在のステージの value を取得（文字列として比較）
    current_stage_value = st.session_state.workflow_stage
    if isinstance(current_stage_value, WorkflowStage):
        current_stage_value = current_stage_value.value
    
    # ワークフロー進行状況を更新（プラン作成完了時）
    if st.session_state.catalog is not None and current_stage_value == WorkflowStage.START.value:
        update_workflow_stage("plan_create")
    #修正_20260409_岡田
    
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
        #ply_generator = GeneratePeopleLikeYouTalk(plan, persona_info)
        explanation_ply = "固定文言"
        #explanation_ply, customer_cluster, special_contract_cluster = ply_generator.run()
        
        #st.session_state.ply_explanation = explanation_ply
        #st.session_state.customer_cluster = customer_cluster
        #st.session_state.special_contract_cluster = special_contract_cluster
        
        #修正_20260409_岡田
        # PLY生成完了後、ワークフローを完了状態に更新
        #update_workflow_stage("end")
        #修正_20260409_岡田
        
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
# ★ ワークフローヘッダー用のスタイルを追加
# ★ ボタン内改行用のスタイルを追加 #20260413
# ★ 処理中メッセージ用のスタイルを追加（吹き出し内にアイコンを含む形式）
# ==============================================================================

st.markdown("""
<style>
     /* ===== 最優先: padding-top 10px 強制適用 ===== */
    .main .block-container,
    .main [data-testid="stMainBlockContainer"],
    [data-testid="stMainBlockContainer"],
    section[data-testid="stMain"] > div,
    section[data-testid="stMain"] > div[data-testid="stMainBlockContainer"],
    div.stMainBlockContainer,
    .st-emotion-cache-1jicfl2,
    .st-emotion-cache-z5fcl4 {
        padding-top: 70px !important;
        padding-left: 10px !important;
         padding-right: 20px !important;
    }
    st-emotion-cache-1j22a0y {
        padding-top: 30px !important;
    }
    /* ★ stAppHeader の padding-top を 20px に設定 #20260413 */
    .stAppHeader,
    [data-testid="stAppHeader"],
    .st-emotion-cache-1up3yna,
    .e1yxiy6j1 {
        padding-top: 20px !important;
    }
    [data-testid="stAppViewContainer"] { overflow: hidden !important; }  #20260410 李修正　画面全体のスクロールを無効化
    [data-testid="stSidebar"] { position: relative !important; height: 100vh !important; background-color: #f8f9fa; border-right: 1px solid #e9ecef; } /* #20260410 李修正　幅と表示の強制を解除 */
    [data-testid="stSidebar"] > div:first-child { position: relative !important; height: 100vh !important; overflow-y: auto !important; }
    [data-testid="stSidebarContent"] { overflow-y: auto !important; height: 100% !important; }
    .main .block-container { padding-top: 40px !important; padding-bottom: 1rem !important; padding-left: 0.25rem !important; padding-right: 0.3rem !important; max-width: 100% !important; }
    header[data-testid="stHeader"] { background: transparent !important; height: 0 !important; min-height: 0 !important; overflow: visible !important; }  #20260410 李修正　ヘッダーの余白を削除しつつ、中にある開閉ボタンは隠さない
    [data-testid="collapsedControl"] { display: flex !important; z-index: 100000 !important; } /* #20260410 李修正　展開ボタンの強制表示（旧バージョン） */
    [data-testid="stSidebarCollapsedControl"] { display: flex !important; z-index: 100000 !important; } /* #20260410 李修正　展開ボタンの強制表示（新バージョン） */
    h1 { font-size: 1.5rem !important; font-weight: 600 !important; color: #1a1a2e !important; margin-bottom: 0.5rem !important; }
    h2, h3, .stSubheader { font-size: 1rem !important; font-weight: 600 !important; color: #16213e !important; margin-bottom: 0.5rem !important; }
    [data-testid="stSidebar"] .stButton > button { background-color: #ffffff; border: 1px solid #dee2e6; color: #495057; font-weight: 500; font-size: 0.875rem; padding: 0.5rem 1rem; border-radius: 6px; }
    /* #20260410 李修正　オプションボタンをクリックした瞬間に全体がグレーになるのを防ぎ、即座に透明にする */
    .stButton > button[disabled] { opacity: 0 !important; visibility: hidden !important; transition: all 0s !important; }
    /* 特約保険料ボタン（disabled=Trueで使うやつ）は例外として表示をキープ */
    [data-testid="stMain"] .stButton:last-of-type > button[disabled] { opacity: 0.5 !important; visibility: visible !important; }
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
    
    /* ★ ワークフローヘッダー用のスタイル（固定ヘッダー・下線削除） */
    .workflow-header {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 9999;
        background-color: #ffffff;
        padding-left: 300px;  /* サイドバーの幅分だけ左にパディング */
    }
    .workflow-container {
        display: flex;
        align-items: center;
        justify-content: flex-start;  /* ← 左寄せに変更 */
        padding: 12px 20px;
        background-color: #ffffff;
    }
    
    /* サイドバーが閉じている時のスタイル調整 */
    @media (max-width: 768px) {
        .workflow-header {
            padding-left: 0;
        }
        .main .block-container {
            padding-top: 70px !important;
        }
    }
    
    /* ★ ボタン内で改行を有効にするスタイル #20260413 */
    .stButton > button {
        white-space: pre-line !important;
        line-height: 1.4 !important;
        text-align: center !important;
    }
    
    /* ★ 処理中メッセージ（吹き出し内にアイコンを含む形式）用のスタイル */
    .processing-bubble {
        display: flex;
        justify-content: flex-start;
        margin: 12px 0;
        padding: 0 0.5rem;
    }
    .processing-bubble-content {
        display: flex;
        align-items: center;
        background-color: #f0f2f6;
        border-radius: 1rem;
        padding: 14px 18px;
        max-width: 85%;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
    }
    /* Streamlitデフォルトのアシスタントアイコンに合わせる #20260416_李修正 */
    .processing-bubble .ai-icon {
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-right: 12px;
        flex-shrink: 0;
    }
    .processing-bubble .ai-icon svg {
        width: 24px;
        height: 24px;
        fill: currentColor;
    }
    .processing-bubble .spinner {
        width: 18px;
        height: 18px;
        border: 3px solid #e9ecef;
        border-top: 3px solid #29A383;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin-right: 12px;
        flex-shrink: 0;
    }
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    .processing-bubble .processing-text {
        color: #495057;
        font-size: 0.95rem;
        line-height: 1.4;
    }
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
budget_personal = current_row.iloc[43]

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
# ★ ボタン配置順序を変更: プラン作成 → チャット履歴クリア #20260413
# ===========================================

with st.sidebar:
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
    <tr class="highlight-row"><td class="label">ご予算</td><td class="value highlight-value">{budget_personal}円</td></tr>
    </table></div>
    """, unsafe_allow_html=True)  #20240409
    st.divider()
    
    # ★ プラン作成ボタンを先に配置 #20260413
    if st.button("プラン作成", key="create_draft_plan_btn", use_container_width=True, type="primary"):
        st.session_state.messages.append({"role": "user", "content": ""})
        st.session_state.button_options = []
        st.session_state.pending_input_display = ""  #20240409 ドラフトプラン作成時は入力欄をクリア
        # ★ 処理中フラグを設定してrerun
        st.session_state.is_processing = True
        st.session_state.processing_message = "ドラフトプラン作成中\n少々お待ちください"
        st.session_state.pending_ai_request = "CREATE_DRAFT_PLAN"  # 特別なフラグ
        st.rerun()
    
    # ★ チャット履歴クリアボタンをプラン作成の下に移動 #20260413
    if st.button("🗑️ チャット履歴をクリア", key="clear_chat_btn", use_container_width=True):
        reset_conversation_state()
        st.rerun()



# ===========================================
# メインエリアのレイアウト

# ===========================================

#修正_20260409_岡田
# ★ メインエリアの一番上にワークフロー進行状況を固定ヘッダーとして表示
render_workflow_progress_header()
#修正_20260409_岡田

col_chat, col_right = st.columns([3, 1])



# ===========================================
# 右側エリア（レーダーチャート + 保障額表示）

# ===========================================

with col_right:
    st.markdown(
        """
        <style>
        /* 右側カラム全体の垂直余白を詰める */
        div[data-testid="column"]:nth-of-type(2) > div > div > div {
            gap: 0.2rem !important;
        }
        div[data-testid="column"]:nth-of-type(2) div[data-testid="stVerticalBlock"] > div > div {
            padding-bottom: 0.1rem !important;
            padding-top: 0.1rem !important;
        }
        </style>
        """, unsafe_allow_html=True
    )
    st.subheader("必要保障額カバー範囲")
    
    # プラン選択ボタン
    plan_col1, plan_col2, plan_col3 = st.columns(3)
    
    with plan_col1:
        matsu_type = "primary" if st.session_state.selected_radar_plan == "松" else "secondary"
        if st.button("松\n(最大限保障)", key="radar_plan_matsu", use_container_width=True, type=matsu_type):
            st.session_state.selected_radar_plan = "松"
            st.rerun()
    
    with plan_col2:
        take_type = "primary" if st.session_state.selected_radar_plan == "竹" else "secondary"
        if st.button("竹\n(ご意向反映)", key="radar_plan_take", use_container_width=True, type=take_type):
            st.session_state.selected_radar_plan = "竹"
            st.rerun()
    
    with plan_col3:
        ume_type = "primary" if st.session_state.selected_radar_plan == "梅" else "secondary"
        if st.button("梅\n(予算反映)", key="radar_plan_ume", use_container_width=True, type=ume_type):
            st.session_state.selected_radar_plan = "梅"
            st.rerun()
    
    #0414李修正st.caption(f"選択中: **{st.session_state.selected_radar_plan}プラン**")
    
    # レーダーチャートを表示
    radar_fig = create_coverage_radar_chart(st.session_state.selected_radar_plan)
    st.plotly_chart(radar_fig, use_container_width=True)
    
    # 保障額詳細を表示（読み取り専用）
    coverage_data = 0
    #coverage_data = get_coverage_data_with_categories(st.session_state.selected_radar_plan)
    
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
    #else:
        #st.info("ドラフトプランを作成すると保障額が表示されます")
    
    # 特約保険料確認ボタン
    st.markdown("")
    has_catalog = st.session_state.catalog is not None
    
    if has_catalog:
    
        # ダイアログ表示フラグの初期化
        if "show_numpad_dialog" not in st.session_state:
            st.session_state.show_numpad_dialog = False
        if "numpad_input" not in st.session_state:
            st.session_state.numpad_input = ""
        if "numpad_confirmed" not in st.session_state:
            st.session_state.numpad_confirmed = False
        
        def format_yen_to_man(yen_value):
            """円を万円表示に変換（例: 5000 → 0.5万円, 10000 → 1万円, 15000 → 1.5万円）"""
            if yen_value <= 0 or yen_value == -999:
                return "なし"
            man = yen_value / 10000
            if man == int(man):
                return f"{int(man)}万円"
            else:
                return f"{man:.1f}万円"
        
        # テンキー入力ダイアログ
        @st.dialog("金額を入力（千円単位）", width="small")
        def show_numpad_dialog():
            state_key = st.session_state.editing_state_key
            
            # テンキー部分をfragmentで囲む（部分更新）
            @st.fragment
            def numpad_fragment():
                # 入力値（千円単位の数値）
                input_val = st.session_state.numpad_input if st.session_state.numpad_input else "0"
                try:
                    thousand_units = int(input_val)
                    yen_value = thousand_units * 1000
                    # ●●●,000円 形式で表示
                    formatted_val = f"{yen_value:,}"
                except:
                    formatted_val = "0"
                
                st.markdown(
                    f"""
                    <div style="text-align: center; font-size: 2em; font-weight: bold; 
                                background-color: #f0f2f6; padding: 16px; border-radius: 8px; 
                                margin-bottom: 16px; font-family: monospace;">
                        {formatted_val} <span style="font-size: 0.6em;">円</span>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
                
                # テンキーレイアウト
                numpad_layout = [
                    ["7", "8", "9"],
                    ["4", "5", "6"],
                    ["1", "2", "3"],
                    ["C", "0", "⌫"]
                ]
                
                for row_idx, row in enumerate(numpad_layout):
                    cols = st.columns(3, gap="small")
                    for i, key in enumerate(row):
                        with cols[i]:
                            # Cボタンは赤系の色で目立たせる
                            if key == "C":
                                st.markdown(
                                    """
                                    <style>
                                    div[data-testid="stButton"]:has(button[kind="secondary"]) button:contains("C") {
                                        background-color: #ff6b6b;
                                        color: white;
                                    }
                                    </style>
                                    """, unsafe_allow_html=True
                                )
                                if st.button("🔄 クリア", use_container_width=True, key=f"numpad_{row_idx}_{i}", type="primary"):
                                    st.session_state.numpad_input = ""
                                    st.rerun(scope="fragment")
                            elif key == "⌫":
                                if st.button(key, use_container_width=True, key=f"numpad_{row_idx}_{i}"):
                                    st.session_state.numpad_input = st.session_state.numpad_input[:-1]
                                    st.rerun(scope="fragment")
                            else:
                                if st.button(key, use_container_width=True, key=f"numpad_{row_idx}_{i}"):
                                    # 最大4桁（9999千円 = 約1000万円）まで
                                    if len(st.session_state.numpad_input) < 4:
                                        st.session_state.numpad_input += key
                                    st.rerun(scope="fragment")
            
            # フラグメント実行
            numpad_fragment()
            
            st.markdown("---")
            
            # 確定・キャンセルボタン（2ボタン構成）
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("✕ キャンセル", use_container_width=True, type="secondary"):
                    st.session_state.show_numpad_dialog = False
                    st.session_state.numpad_input = ""
                    st.rerun()
            
            with col2:
                if st.button("✓ 確定", use_container_width=True, type="primary"):
                    try:
                        thousand_units = int(st.session_state.numpad_input) if st.session_state.numpad_input else 0
                        val = thousand_units * 1000  # 千円単位 → 円に変換
                    except:
                        val = 0
                    st.session_state[st.session_state.editing_state_key] = val if val > 0 else -999
                    st.session_state.show_numpad_dialog = False
                    st.session_state.numpad_input = ""
                    st.session_state.numpad_confirmed = True
                    st.rerun()
        
        # ダイアログ表示（フラグがTrueの場合）
        if st.session_state.show_numpad_dialog:
            show_numpad_dialog()
        
        if st.button("全プラン詳細確認", key="special_contract_btn", use_container_width=True, type="secondary"):
            show_special_contract_premium_dialog()
                
        st.markdown(f"**詳細調整 ({st.session_state.selected_radar_plan}プラン)**")
        
        CATEGORY_ABBR = {
            "病気・ケガへの備え": "病気",
            "がん保障": "がん",
            "循環器病保障": "循環器",
            "特定重度疾病保障": "重度疾病",
            "障害・就労不能保障": "障害就労",
            "健康促進保障": "健康促進",
        }
        
        selected_plan_name = st.session_state.selected_radar_plan
        plan_type_map = {"松": PlanType.MATSU, "竹": PlanType.TAKE, "梅": PlanType.UME}
        selected_plan_type = plan_type_map.get(selected_plan_name)
        
        catalog = st.session_state.catalog
        plan = catalog.get(selected_plan_type) if catalog and selected_plan_type else None
        
        if plan:
            st.markdown(
                """
                <style>
                .cat-badge {
                    background-color: #f0f2f6; 
                    padding: 4px 8px; 
                    font-size: 0.8em; 
                    font-weight: bold; 
                    border-radius: 2px;
                    display: inline-block;
                }
                .contract-name {
                    font-size: 0.85em; 
                    font-weight: 500;
                    line-height: 1.2;
                }
                </style>
                """, unsafe_allow_html=True
            )
            
            detail_container = st.container(height=350)
            with detail_container:
                for attr_name, category_name in SPECIAL_CONTRACT_CATEGORY_ORDER:
                    contracts = getattr(plan, attr_name, {})
                    if not contracts:
                        continue
                    
                    abbr = CATEGORY_ABBR.get(category_name, category_name)
                    
                    color_map = {
                        "病気": "#F17079",
                        "がん": "#F37932",
                        "循環器": "#F37932",
                        "重度疾病": "#F37932",
                        "障害就労": "#6FBF54",
                        "健康促進": "#00A78E",
                    }
                    badge_color = color_map.get(abbr, "#667eea")
                    
                    for contract_type, contract_info in contracts.items():
                        contract_name = contract_type.value if hasattr(contract_type, 'value') else str(contract_type)
                        benefit_amount = contract_info.benefit_amount_yen
                        
                        state_key = f"adj_{selected_plan_name}_{attr_name}_{contract_name}"
                        orig_state_key = f"orig_{state_key}"
                        
                        if state_key not in st.session_state:
                            st.session_state[state_key] = benefit_amount
                        if orig_state_key not in st.session_state:
                            st.session_state[orig_state_key] = benefit_amount if benefit_amount > 0 else 0
                        
                        current_val = st.session_state[state_key]
                        is_toggle_type = (st.session_state[orig_state_key] == 0)
                        
                        # session_stateの値をcontract_infoに反映
                        contract_info.benefit_amount_yen = current_val
                        
                        # カラムレイアウト
                        c1, c2, c3 = st.columns([1.5, 5, 3])
                        
                        with c1:
                            st.markdown(f'<div class="cat-badge" style="border-left: 4px solid {badge_color}; margin-top: 6px;">{abbr}</div>', unsafe_allow_html=True)
                        with c2:
                            st.markdown(f'<div class="contract-name" style="margin-top: 8px;">{contract_name}</div>', unsafe_allow_html=True)
                        
                        with c3:
                            if is_toggle_type:
                                # トグル形式
                                if current_val == -999:
                                    display_text = "なし"
                                    btn_type = "secondary"
                                else:
                                    display_text = "付加"
                                    btn_type = "primary"
                                
                                if st.button(
                                    display_text, 
                                    key=f"toggle_{state_key}", 
                                    use_container_width=True, 
                                    type=btn_type
                                ):
                                    if current_val == -999:
                                        st.session_state[state_key] = 0
                                    else:
                                        st.session_state[state_key] = -999
                                    st.rerun()
                            else:
                                # 数値型：ボタンクリックでテンキーダイアログを開く
                                # 万円単位で表示
                                display_text = format_yen_to_man(current_val)
                                btn_type = "secondary" if current_val == -999 else "primary"
                                
                                if st.button(
                                    display_text, 
                                    key=f"val_btn_{state_key}", 
                                    use_container_width=True,
                                    type=btn_type
                                ):
                                    st.session_state.show_numpad_dialog = True
                                    st.session_state.editing_state_key = state_key
                                    st.session_state.editing_current_val = current_val if current_val != -999 else st.session_state[orig_state_key]
                                    # 初期値をセット（千円単位の数値として）
                                    if current_val != -999 and current_val > 0:
                                        st.session_state.numpad_input = str(current_val // 1000)
                                    else:
                                        st.session_state.numpad_input = ""
                                    st.rerun()
                                
    else:
        st.button("全プラン詳細確認", key="special_contract_btn_disabled", use_container_width=True, disabled=True, help="ドラフトプランを作成すると利用可能になります")



# ===========================================
# チャットエリア

# ===========================================

with col_chat:
    #st.title("AI チャットアシスタント")  #20260413修正
    st.caption(f"選択中のお客さま: **{persona_names[selected_idx]}**（{gender}-{age}才）")  #20240409 性別と年齢を追加
    
    # 高さを指定してスクロール可能なチャットコンテナに変更 #20260410 李修正　
    # ここで高さを指定すると、この枠の中だけがスクロールするようになります
    chat_container = st.container(height=750)  #20260410 李修正　チャット専用のスクロール領域
    
    with chat_container:
        # 最後のユーザーメッセージのインデックスを特定する #20260410 李修正　
        last_user_idx = -1  #20260410 李修正　
        for i, msg in enumerate(st.session_state.messages):  #20260410 李修正　
            if msg["role"] == "user":  #20260410 李修正　
                last_user_idx = i  #20260410 李修正　

        for i, message in enumerate(st.session_state.messages):
            with st.chat_message(message["role"]):
                # 以前のスクロール用アンカーは不要となったため削除 #20260414_李修正
                if message["content"] == "":
                    st.markdown("*プラン作成*")
                else:
                    st.markdown(message["content"])
        
        status = st.session_state.status_flg
        
        if st.session_state.button_options and not st.session_state.get("pending_ai_request") and not st.session_state.get("is_processing"):  #20260410
            #0414李修正　st.markdown("---")
            st.markdown("**以下から選択してください：**")
            
            btn_container = st.container()  #20260410 李修正　インライン配置用のコンテナ
            with btn_container:
                st.markdown('<div class="options-container-anchor"></div>', unsafe_allow_html=True)  #20260410 李修正　CSS適用用の目印
                for idx, option in enumerate(st.session_state.button_options):
                    # 幅を自動調整にするため use_container_width=False に変更 #20260410
                    st.button(option, key=f"button_option_{idx}", use_container_width=False, on_click=handle_option_click, args=(option, None))  #20260410 #修正_20260409_岡田
        
        elif (status in (StatusFlg.OPTIONS, "OPTIONS", "StatusFlg.OPTIONS", "options")
              and not st.session_state.button_options
              and not st.session_state.ply_shown
              and not st.session_state.get("pending_ai_request")
              and not st.session_state.get("is_processing")):  #20260410 李修正　AIリクエスト待機中は表示しない
            st.markdown("---")
            st.markdown("**AIにどのようなことを尋ねますか？**")
            
            #修正_20260409_岡田
            # ★ アクション一覧ボタンとワークフロー更新の対応 #20260413
            # ★ 表示テキスト（改行あり）とAI送信用テキスト（改行なし）を分離
            # ★ 改行位置を調整して上下の文字数をバランス良く配置
            option_buttons = [
                ("1", "「プラン説明」カテゴリー\nについて詳しく説明してください", "プランについて説明してください", "plan_detail_start"),
                ("2", "「プラン修正」保障を手厚くする\n方針で修正してください", "保障を手厚くする方針でプランを修正してください", "plan_modify_start"),
                ("3", "「プラン修正」保険料を下げる\n方針で修正してください", "保険料を下げる方針でプランを修正してください", "plan_modify_start"),
                ("4", "「提案文作成」お客さま向けの\n提案文を作成してください", "お客さまへ向けた提案文章を作成してください", "plan_propose_start"),
                ("5", "「プラン説明」プランの保障\n内容について詳しく説明ください", "保障内容について教えてください", "plan_detail_start")
            ]


            #修正_20260409_岡田
            
            # 最大文字数に基づいて列数を決定（AI送信用テキストで判定）
            texts = [ai_text for _, _, ai_text, _ in option_buttons]  #20260413 修正
            max_len = max(len(t) for t in texts) if texts else 0
            if max_len <= 15:
                cols_per_row = min(4, len(option_buttons))
            elif max_len <= 25:
                cols_per_row = min(3, len(option_buttons))
            elif max_len <= 40:
                cols_per_row = min(2, len(option_buttons))
            else:
                cols_per_row = 1
            
            # ボタンを行ごとに表示
            for row_start in range(0, len(option_buttons), cols_per_row):
                row_options = option_buttons[row_start:row_start + cols_per_row]
                cols = st.columns(cols_per_row)
                for col_idx, (num, display_text, ai_text, workflow_action) in enumerate(row_options):  #20260413 修正
                    with cols[col_idx]:
                        # ★ 表示はdisplay_text（改行あり）、AIにはai_text（改行なし）を送信 #20260413
                        st.button(display_text, key=f"option_{num}", use_container_width=True, on_click=handle_option_click, args=(ai_text, workflow_action))

        
        elif (status in (StatusFlg.PROPOSAL, "PROPOSAL", "StatusFlg.PROPOSAL", "proposal")
              and not st.session_state.get("pending_ai_request")
              and not st.session_state.get("is_processing")):  #20260410 李修正　AIリクエスト待機中は表示しない
            st.markdown("---")
            st.markdown("**プランを選択してください**")
            
            col_matsu, col_take, col_ume = st.columns(3)
            
            with col_matsu:
                if st.button("🥇 松", key="plan_matsu", use_container_width=True):
                    st.session_state.messages.append({"role": "user", "content": "松プランを選択します"})
                    st.session_state.selected_radar_plan = "松"
                    st.session_state.pending_input_display = "松プランを選択します"
                    # ★ 処理中フラグを設定
                    st.session_state.is_processing = True
                    st.session_state.processing_message = get_spinner_text("松プランを選択します")
                    st.session_state.pending_ai_request = "PLAN_松"
                    st.rerun()
            
            with col_take:
                if st.button("🥈 竹", key="plan_take", use_container_width=True):
                    st.session_state.messages.append({"role": "user", "content": "竹プランを選択します"})
                    st.session_state.selected_radar_plan = "竹"
                    st.session_state.pending_input_display = "竹プランを選択します"
                    # ★ 処理中フラグを設定
                    st.session_state.is_processing = True
                    st.session_state.processing_message = get_spinner_text("竹プランを選択します")
                    st.session_state.pending_ai_request = "PLAN_竹"
                    st.rerun()
            
            with col_ume:
                if st.button("🥉 梅", key="plan_ume", use_container_width=True):
                    st.session_state.messages.append({"role": "user", "content": "梅プランを選択します"})
                    st.session_state.selected_radar_plan = "梅"
                    st.session_state.pending_input_display = "梅プランを選択します"
                    # ★ 処理中フラグを設定
                    st.session_state.is_processing = True
                    st.session_state.processing_message = get_spinner_text("梅プランを選択します")
                    st.session_state.pending_ai_request = "PLAN_梅"
                    st.rerun()
        
        # ★ 処理中メッセージをチャットボックス内の最下部に表示（吹き出し内にアイコンを含む形式）
        if st.session_state.get("is_processing") and st.session_state.get("processing_message"):
            # ★ カスタムHTML吹き出しで表示（AIアイコンを吹き出し内に含める）
            st.markdown(f"""
            <div class="processing-bubble">
                <div class="processing-bubble-content">
                    <!-- Streamlitデフォルトの黄色背景アシスタントアイコン #20260416_李修正_v2 -->
                    <div class="ai-icon" style="background-color: rgb(255, 237, 213); border-radius: 5px; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;">
                        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" xmlns="http://www.w3.org/2000/svg" color="inherit" style="width: 20px; height: 20px;"><path d="M12.0003 3.51351C11.3967 3.51351 10.8716 3.86486 10.6354 4.37838C10.6354 4.37838 10.1625 5.56757 9.87324 6.27027H6.74824C5.77662 6.27027 4.98878 7.05405 4.98878 8.02703V15.7568C4.98878 16.7297 5.77662 17.5135 6.74824 17.5135H17.2523C18.2239 17.5135 19.0118 16.7297 19.0118 15.7568V8.02703C19.0118 7.05405 18.2239 6.27027 17.2523 6.27027H14.1273C13.8381 5.56757 13.3651 4.37838 13.3651 4.37838C13.1289 3.86486 12.6039 3.51351 12.0003 3.51351Z" fill="#ffbd45"></path><path d="M10.2435 13.1351C10.2435 13.7297 9.77051 14.2162 9.16686 14.2162C8.56321 14.2162 8.09021 13.7297 8.09021 13.1351C8.09021 12.5405 8.56321 12.0541 9.16686 12.0541C9.77051 12.0541 10.2435 12.5405 10.2435 13.1351Z" fill="#121212"></path><path d="M15.9103 13.1351C15.9103 13.7297 15.4373 14.2162 14.8337 14.2162C14.23 14.2162 13.757 13.7297 13.757 13.1351C13.757 12.5405 14.23 12.0541 14.8337 12.0541C15.4373 12.0541 15.9103 12.5405 15.9103 13.1351Z" fill="#121212"></path><path d="M21.5034 8.54054C21.7661 8.54054 21.9763 8.75676 21.9763 9.02703V11.9459C21.9763 12.2162 21.7661 12.4324 21.5034 12.4324C21.2407 12.4324 21.0305 12.2162 21.0305 11.9459V9.02703C21.0305 8.75676 21.2407 8.54054 21.5034 8.54054Z" fill="#ffbd45"></path><path d="M2.49733 8.54054C2.76005 8.54054 2.97027 8.75676 2.97027 9.02703V11.9459C2.97027 12.2162 2.76005 12.4324 2.49733 12.4324C2.23461 12.4324 2.02438 12.2162 2.02438 11.9459V9.02703C2.02438 8.75676 2.23461 8.54054 2.49733 8.54054Z" fill="#ffbd45"></path><path d="M12.0003 14.7568C13.2084 14.7568 14.2852 14.4324 15.0205 13.9189C15.3359 13.7568 15.6512 14.027 15.5461 14.3784C14.9942 16.0811 13.6289 17.2973 12.0003 17.2973C10.3718 17.2973 9.00643 16.0811 8.4545 14.3784C8.34938 14.027 8.66477 13.7568 8.98015 13.9189C9.71544 14.4324 10.7923 14.7568 12.0003 14.7568Z" fill="#121212"></path></svg>
                    </div>
                    <div class="spinner"></div>
                    <div class="processing-text">{st.session_state.processing_message}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    # 常に画面下部に固定される公式チャット入力コンポーネントに変更 #20260410 李修正　
        # ★ ここにチャット入力ボックスを追加
    if prompt := st.chat_input("メッセージを入力してください"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.button_options = []
        st.session_state.pending_input_display = ""
        st.session_state.pending_ai_request = prompt
        st.session_state.should_scroll_to_user = False
        # ★ 処理中フラグを設定
        st.session_state.is_processing = True
        st.session_state.processing_message = get_spinner_text(prompt)
        st.rerun()

    # ==============================================================================
    # 遅延実行されるAIリクエストの処理 #20260410 李修正　
    # ==============================================================================
    if st.session_state.get("pending_ai_request"):  #20260410 李修正　
        request_text = st.session_state.pending_ai_request  #20260410 李修正　
        st.session_state.pending_ai_request = None  #20260410 李修正　フラグをクリア
        
        try:  #20260410 李修正　
            # ★ ドラフトプラン作成の場合の特殊処理
            if request_text == "CREATE_DRAFT_PLAN":
                if st.session_state.status_flg in (StatusFlg.PROPOSAL, "PROPOSAL", "StatusFlg.PROPOSAL", "proposal"):
                    explanation_ply = generate_ply_proposal()
                    st.session_state.messages.append({"role": "assistant", "content": explanation_ply})
                    st.session_state.status_flg = ""
                    st.session_state.ply_shown = True
                else:
                    ai_response = call_chat_api("")
                    st.session_state.messages.append({"role": "assistant", "content": ai_response})
                
                sync_coverage_dict_from_catalog()
            
            # プラン選択の場合の特殊処理 #20260410 李修正　
            elif request_text.startswith("PLAN_"):  #20260410 李修正　
                plan_name = request_text.replace("PLAN_", "")  #20260410 李修正　
                plan_enum = PlanType.MATSU if plan_name == "松" else (PlanType.TAKE if plan_name == "竹" else PlanType.UME)  #20260410 李修正　
                result_text = generate_ply_proposal(plan_enum)  #20260410 李修正　
                st.session_state.messages.append({"role": "assistant", "content": result_text})  #20260410 李修正　
                st.session_state.status_flg = ""  #20260410 李修正　
                st.session_state.ply_shown = True  #20260410 李修正　
                sync_coverage_dict_from_catalog()
            
            # 通常の提案やチャットの場合 #20260410 李修正　
            elif st.session_state.status_flg in (StatusFlg.PROPOSAL, "PROPOSAL", "StatusFlg.PROPOSAL", "proposal"):  #20260410 李修正　
                explanation_ply = generate_ply_proposal()  #20260410 李修正　
                st.session_state.messages.append({"role": "assistant", "content": explanation_ply})  #20260410 李修正　
                st.session_state.status_flg = ""  #20260410 李修正　
                st.session_state.ply_shown = True  #20260410 李修正　
            else:  #20260410 李修正　
                ai_response = call_chat_api(request_text)  #20260410 李修正　
                st.session_state.messages.append({"role": "assistant", "content": ai_response})  #20260410 李修正　
            
            sync_coverage_dict_from_catalog()  #20260410 李修正　
            
        except Exception as e:  #20260410 李修正　
            st.session_state.messages.append({"role": "assistant", "content": f"エラーが発生しました: {str(e)}"})  #20260410 李修正　
        
        # ★ 処理完了後、処理中フラグをクリア
        st.session_state.is_processing = False
        st.session_state.processing_message = ""
        st.session_state.should_scroll_to_user = True  #20260410 李修正　回答が終わったらスクロールするようにフラグを立てる
        st.rerun()  #20260410 李修正　処理完了後に画面を最終更新


st.markdown("""
<style>
    [data-testid="stSidebarResizer"]{ width: 1px !important; background: #d0d7de !important; }
    /* #20260410 李修正　開閉ボタンの非表示設定を削除し、トグル可能に戻す */
    section[data-testid="stMain"]{ padding-left: 0.5rem !important; overflow: hidden !important; height: 100vh !important; }  #20260410 李修正　メインエリアを固定
    section[data-testid="stMain"] .block-container{ padding-left: 10px !important; height: 100vh !important; overflow: hidden !important; padding-top: 70px !important;  padding-right: 20px !important; max-width: 100% !important; } #20260410 李修正　内部も固定し余白調整
    [data-testid="stMainBlockContainer"] { padding-top: 70px !important; padding-left: 10px !important; padding-right: 20px !important;} /* Streamlitの新バージョン用 */

    /* ============================================================================== */
    /* 全局チャット吹き出し（気泡）スタイル上書き #20260414_李修正 */
    /* ============================================================================== */
    /* stChatMessageコンテナ自体のパディングなどを微調整 */
    div[data-testid="stChatMessage"] {
        padding: 0.5rem 1rem !important;
        border-radius: 10px !important;
        margin-bottom: 0.5rem !important;
        background-color: transparent !important;
        display: flex !important;
        align-items: flex-start !important;
    }
    
    /* ユーザーの発言（ユーザーアバターを持つメッセージ）*/
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]),
    div[data-testid="stChatMessage"]:has(div[class*="user"]) {
        flex-direction: row-reverse !important; /* アバターを右に配置 */
        max-width: fit-content !important;  /* ★追加：幅を内容に合わせる */
    }
    
    /* ★修正：ユーザーメッセージの親コンテナを確実に右に押しやる #20260416_李修正_v3 */
    div[data-testid="stVerticalBlock"] > div:has(div[data-testid="stChatMessageAvatarUser"]),
    div[data-testid="stVerticalBlock"] > div:has(div[data-testid="stChatMessage"]:has(div[class*="user"])) {
        display: flex !important;
        justify-content: flex-end !important;
        width: 100% !important;
        margin-left: auto !important; /* コンテナ全体を右へ */
    }
    
    /* 1.38.0 の仕様上、更に内側の div も右寄せする必要がある場合 */
    div[data-testid="stVerticalBlock"] > div:has(div[data-testid="stChatMessage"]:has(div[class*="user"])) > div {
        margin-left: auto !important;
    }

    /* ユーザーのテキスト吹き出し部分 */
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) div[data-testid="stMarkdownContainer"],
    div[data-testid="stChatMessage"]:has(div[class*="user"]) div[data-testid="stMarkdownContainer"] {
        background-color: #C9E8E0 !important; /* カスタム緑色 #20260414_李修正 */
        color: #000000 !important;
        padding: 10px 15px !important;
        border-radius: 12px !important; /* 全て角丸にする #20260414_李修正 */
        box-shadow: 0 1px 2px rgba(0,0,0,0.1) !important;
        margin-right: 10px !important;
        margin-left: auto !important; /* ★修正：左側マージンを自動にして右に寄せる */
        display: inline-block !important;
        border: none !important; /* 破れや余計な枠線を防ぐ #20260414_李修正 */
    }
    
    /* ユーザーのテキスト吹き出し部分の親要素（テキストコンテナ）も右寄せにする */
    div[data-testid="stChatMessage"]:has(div[class*="user"]) div[data-testid="chatAvatarIcon-user"] + div,
    div[data-testid="stChatMessage"]:has(div[class*="user"]) > div:nth-child(2) {
        margin-left: auto !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: flex-end !important;
    }

    /* AIアシスタントの発言（アシスタントアバターを持つメッセージ）*/
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarAssistant"]),
    div[data-testid="stChatMessage"]:has(div[class*="assistant"]) {
        flex-direction: row !important; /* アバターを左に配置 */
        max-width: fit-content !important;  /* ★追加：幅を内容に合わせる */
    }
    
    /* ★追加：AIアシスタントのメッセージ親コンテナを左寄せ（Streamlit 1.38対応） #20260416_李修正 */
    div[data-testid="stVerticalBlock"] > div:has(div[data-testid="stChatMessageAvatarAssistant"]),
    div[data-testid="stVerticalBlock"] > div:has(div[data-testid="stChatMessage"] div[class*="assistant"]) {
        display: flex !important;
        justify-content: flex-start !important;
        width: 100% !important;
    }

    /* AIアシスタントのテキスト吹き出し部分 */
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarAssistant"]) div[data-testid="stMarkdownContainer"],
    div[data-testid="stChatMessage"]:has(div[class*="assistant"]) div[data-testid="stMarkdownContainer"] {
        background-color: #F0F2F6 !important; /* カスタム灰色 #20260414_李修正 */
        color: #333333 !important;
        padding: 10px 15px !important;
        border-radius: 12px !important; /* 全て角丸にする #20260414_李修正 */
        border: none !important; /* 枠線を削除 #20260414_李修正 */
        box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
        margin-left: 10px !important;
        margin-right: 50px !important;
        display: inline-block !important;
    }
    
    div[data-testid="stChatMessage"] div[data-testid="stMarkdownContainer"] > *:last-child {
        margin-bottom: 0 !important;
        padding-bottom : 0 !important;
        }


    /* アバター画像のサイズ調整 */
    div[data-testid="stChatMessageAvatarUser"],
    div[data-testid="stChatMessageAvatarAssistant"] {
        width: 35px !important;
        height: 35px !important;
        min-width: 35px !important;
    }
</style>
""", unsafe_allow_html=True)


