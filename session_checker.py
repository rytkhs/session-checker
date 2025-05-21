import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import json
import os
from datetime import datetime
import pickle
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

# --- 設定 ---
INITIAL_URL = os.getenv("INITIAL_URL", "https://example.com/dashboard")
MANUAL_LOGIN_WAIT_SECONDS = int(os.getenv("MANUAL_LOGIN_WAIT_SECONDS", "60"))
POST_ACCESS_WAIT_SECONDS = int(os.getenv("POST_ACCESS_WAIT_SECONDS", "10"))
INITIAL_WAIT_TIME = int(os.getenv("INITIAL_WAIT_TIME", "55"))
WAIT_TIME_INCREMENT = int(os.getenv("WAIT_TIME_INCREMENT", "5"))
COOKIES_FILE = os.getenv("COOKIES_FILE", "saved_cookies.json")
SESSION_FILE = os.getenv("SESSION_FILE", "selenium_session.pkl")
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
CHROME_PROFILE_DIR = os.getenv("CHROME_PROFILE_DIR", "chrome_profile")
# --- 設定ここまで ---

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("session_check.log", encoding="utf-8"),  # ファイルエンコーディングを指定
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def setup_driver():
    """WebDriverのセットアップ"""
    chrome_options = Options()
    # ユーザーエージェントを設定
    chrome_options.add_argument(f"user-agent={USER_AGENT}")
    chrome_options.add_argument("--window-size=1920x1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    # 永続的なプロファイルを使用
    user_data_dir = os.path.join(os.getcwd(), CHROME_PROFILE_DIR)
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")

    try:
        driver = webdriver.Chrome(options=chrome_options)
        # WebDriverを検出されにくくするための追加設定
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        logger.info("WebDriver (Chrome) のセットアップが完了しました。")
        return driver
    except Exception as e:
        logger.error(f"WebDriverのセットアップ中にエラーが発生しました: {e}")
        logger.error("ChromeDriverがシステムのPATHに含まれているか、または正しいバージョンか確認してください。")
        raise

def save_cookies_to_file(cookies):
    """Cookieをファイルに保存"""
    try:
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False, indent=4)
        logger.info(f"Cookieを '{COOKIES_FILE}' に保存しました。")
        return True
    except Exception as e:
        logger.error(f"Cookieの保存に失敗しました: {e}")
        return False

def load_cookies_from_file():
    """ファイルからCookieを読み込み"""
    if not os.path.exists(COOKIES_FILE):
        logger.warning(f"Cookieファイル '{COOKIES_FILE}' が見つかりません。")
        return None

    try:
        with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        logger.info(f"'{COOKIES_FILE}' から {len(cookies)} 個のCookieを読み込みました。")
        return cookies
    except Exception as e:
        logger.error(f"Cookieファイルの読み込みに失敗しました: {e}")
        return None

def save_local_storage(driver, key_list=None):
    """LocalStorageの内容を保存"""
    try:
        # 全てのキーを取得
        if key_list is None:
            key_list = driver.execute_script("return Object.keys(localStorage);")

        # キーと値のペアを辞書に格納
        storage_data = {}
        for key in key_list:
            value = driver.execute_script(f"return localStorage.getItem('{key}');")
            storage_data[key] = value

        # セッションストレージも保存
        session_keys = driver.execute_script("return Object.keys(sessionStorage);")
        session_data = {}
        for key in session_keys:
            value = driver.execute_script(f"return sessionStorage.getItem('{key}');")
            session_data[key] = value

        combined_data = {
            "localStorage": storage_data,
            "sessionStorage": session_data
        }

        # ファイルに保存
        with open(SESSION_FILE, 'wb') as f:
            pickle.dump(combined_data, f)

        logger.info(f"ストレージデータを '{SESSION_FILE}' に保存しました。（localStorage: {len(storage_data)}個, sessionStorage: {len(session_data)}個）")
        return True
    except Exception as e:
        logger.error(f"ストレージデータの保存に失敗: {e}")
        return False

def restore_local_storage(driver):
    """保存したLocalStorageを復元"""
    if not os.path.exists(SESSION_FILE):
        logger.warning(f"セッションファイル '{SESSION_FILE}' が見つかりません。")
        return False

    try:
        with open(SESSION_FILE, 'rb') as f:
            storage_data = pickle.load(f)

        # LocalStorageの復元
        for key, value in storage_data.get("localStorage", {}).items():
            if value:  # 空でないデータのみ復元
                try:
                    driver.execute_script(f"localStorage.setItem('{key}', '{value}');")
                except Exception as e:
                    logger.warning(f"LocalStorageキー '{key}' の復元に失敗: {e}")

        # SessionStorageの復元
        for key, value in storage_data.get("sessionStorage", {}).items():
            if value:  # 空でないデータのみ復元
                try:
                    driver.execute_script(f"sessionStorage.setItem('{key}', '{value}');")
                except Exception as e:
                    logger.warning(f"SessionStorageキー '{key}' の復元に失敗: {e}")

        logger.info(f"ストレージデータを復元しました。")
        return True
    except Exception as e:
        logger.error(f"ストレージデータの復元に失敗: {e}")
        return False

def extract_auth_tokens(driver):
    """認証関連のトークンを探して記録（デバッグ用）"""
    try:
        # LocalStorageからトークン関連の情報を探す
        storage_keys = driver.execute_script("return Object.keys(localStorage);")
        auth_keys = [key for key in storage_keys if any(term in key.lower() for term in
                    ['token', 'auth', 'jwt', 'session', 'login', 'user', 'credential'])]

        if auth_keys:
            logger.info(f"認証関連のLocalStorageキー: {auth_keys}")
            for key in auth_keys:
                value_preview = driver.execute_script(f"return localStorage.getItem('{key}').substring(0, 50);")
                logger.info(f"キー '{key}' の値（先頭50文字）: {value_preview}...")
        else:
            logger.info("LocalStorageに認証関連のキーは見つかりませんでした。")

        # Cookieから認証関連の情報を探す
        auth_cookies = [c for c in driver.get_cookies() if any(term in c['name'].lower() for term in
                      ['token', 'auth', 'jwt', 'session', 'login', 'user', 'credential'])]

        if auth_cookies:
            logger.info(f"認証関連のCookie: {[c['name'] for c in auth_cookies]}")
        else:
            logger.info("認証関連のCookieは見つかりませんでした。")

        return True
    except Exception as e:
        logger.error(f"認証トークンの抽出に失敗: {e}")
        return False

def main():
    logger.info("セッション有効性チェックツールを開始します。")
    logger.info(f"対象URL: {INITIAL_URL}")

    driver = None
    saved_cookies = None

    # 保存されたCookieがあれば読み込む
    saved_cookies = load_cookies_from_file()
    if saved_cookies and os.path.exists(SESSION_FILE):
        logger.info("保存されたセッションデータを使用します。手動ログインステップをスキップします。")
        is_first_login = False
    else:
        logger.info("保存されたセッションデータが見つかりません。手動ログインが必要です。")
        is_first_login = True

    try:
        if is_first_login:
            # --- ステップ 1：初回アクセスとログイン ---
            logger.info("ステップ1: 初回アクセスとログイン処理を開始します。")
            driver = setup_driver()

            logger.info(f"'{INITIAL_URL}' にアクセスします...")
            driver.get(INITIAL_URL)
            logger.info(f"アクセス成功。現在のURL: {driver.current_url}")

            if INITIAL_URL not in driver.current_url:
                logger.info("ログインページにリダイレクトされたようです。")

            logger.info(f"{MANUAL_LOGIN_WAIT_SECONDS}秒間ブラウザを開いたままにします。手動でログインしてください...")
            time.sleep(MANUAL_LOGIN_WAIT_SECONDS)

            logger.info("手動ログイン時間が終了しました。")

            # ログイン後のURLを確認
            logger.info(f"ログイン後のURL: {driver.current_url}")
            if INITIAL_URL not in driver.current_url and "login" in driver.current_url.lower():
                logger.warning("まだログインページにいる可能性があります。ログインが成功したか確認してください。")
                logger.warning("このまま続行しますが、セッションが取得できていない可能性があります。")

            # JavaScriptの実行を待つ余裕を持たせる
            logger.info("ページが完全に読み込まれるまで追加で5秒待機します...")
            time.sleep(5)

            # 認証関連のトークンを探して記録（デバッグ用）
            extract_auth_tokens(driver)

            # LocalStorageとSessionStorageを保存
            save_local_storage(driver)

            saved_cookies = driver.get_cookies()
            if saved_cookies:
                logger.info(f"{len(saved_cookies)}個のCookieを保持しました。")
                # Cookieをファイルに保存
                save_cookies_to_file(saved_cookies)
            else:
                logger.warning("Cookieが取得できませんでした。ログインに失敗したか、サイトがCookieを使用していない可能性があります。")
                # Cookieがなければ続行する意味がないので終了
                return

            logger.info("ブラウザを閉じます。")
            driver.quit()
            driver = None # driverオブジェクトをクリア

        # --- ステップ 2：セッション有効性チェックループ ---
        logger.info("ステップ2: セッション有効性チェックループを開始します。")
        loop_count = 0
        while True:
            loop_count += 1
            logger.info(f"--- ループ {loop_count} ---")

            # ループカウントによって待機時間を増加させる
            wait_time = (INITIAL_WAIT_TIME + (loop_count - 1) * WAIT_TIME_INCREMENT) * 60
            logger.info(f"{wait_time // 60}分{wait_time % 60}秒後に次のチェックを行います。 (合計 {wait_time}秒)")
            time.sleep(wait_time)

            # 保存されたCookieが古い場合は再取得
            if os.path.exists(COOKIES_FILE):
                file_timestamp = os.path.getmtime(COOKIES_FILE)
                file_age_hours = (datetime.now().timestamp() - file_timestamp) / 3600
                if file_age_hours > 24:  # 24時間以上経過していたら警告
                    logger.warning(f"Cookieファイルが {file_age_hours:.1f} 時間前に保存されたもので古い可能性があります。")

            logger.info("保持しているセッションデータを使用して再度アクセスします。")
            driver = setup_driver() # 新しいブラウザインスタンス

            # Cookieをセットする前に、一度対象ドメインにアクセスする必要がある
            # INITIAL_URLからドメインを取得
            try:
                from urllib.parse import urlparse
                parsed_url = urlparse(INITIAL_URL)
                domain_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                logger.info(f"ドメイン '{domain_url}' にアクセスします...")
                driver.get(domain_url) # ドメインのルートにアクセス
                time.sleep(3) # Cookieを設定するドメインコンテキストを確立するための待機
            except Exception as e:
                logger.warning(f"ドメインへの初期アクセスに失敗しました: {e}。INITIAL_URLに直接アクセスします。")
                driver.get(INITIAL_URL) # フォールバック
                time.sleep(3)

            # LocalStorageとSessionStorageを復元
            restore_local_storage(driver)

            logger.info(f"Cookieをセットします...")
            cookie_success_count = 0
            cookie_error_count = 0
            for cookie in saved_cookies:
                # 'expiry' キーが存在し、かつ浮動小数点数である場合、整数に変換
                if 'expiry' in cookie and isinstance(cookie['expiry'], float):
                    cookie['expiry'] = int(cookie['expiry'])
                try:
                    driver.add_cookie(cookie)
                    cookie_success_count += 1
                except Exception as e:
                    cookie_error_count += 1
                    logger.warning(f"Cookieの追加に失敗しました: {cookie.get('name', 'N/A')}, エラー: {e}")

            logger.info(f"{cookie_success_count}個のCookieを正常にセットしました。{cookie_error_count}個のCookieはエラーでした。")

            # ページの再読み込みでCookieを適用
            driver.refresh()
            time.sleep(3)

            logger.info(f"'{INITIAL_URL}' にアクセスします...")
            driver.get(INITIAL_URL)
            time.sleep(5)  # ページ読み込みと処理待ちを長めに
            logger.info(f"アクセス後のURL: {driver.current_url}")

            # LocalStorageとSessionStorageの状態を出力 (デバッグ用)
            try:
                local_storage = driver.execute_script("return Object.keys(localStorage);")
                session_storage = driver.execute_script("return Object.keys(sessionStorage);")
                logger.info(f"LocalStorage keys: {local_storage}")
                logger.info(f"SessionStorage keys: {session_storage}")
            except Exception as e:
                logger.warning(f"ストレージ情報の取得に失敗: {e}")

            logger.info(f"{POST_ACCESS_WAIT_SECONDS}秒間待機します...")
            time.sleep(POST_ACCESS_WAIT_SECONDS)

            current_url_after_wait = driver.current_url
            logger.info(f"待機後の最終的なURL: {current_url_after_wait}")

            # ページのHTMLソースを取得してデバッグ情報としてログに出力
            try:
                page_source = driver.page_source[:500]  # 最初の500文字だけ表示
                logger.info(f"ページソース (先頭部分): {page_source}...")
            except Exception as e:
                logger.warning(f"ページソースの取得に失敗: {e}")

            # URLの末尾のスラッシュやクエリパラメータの違いを許容するため、より柔軟な比較を行う
            is_session_valid = False
            if INITIAL_URL.rstrip('/') == current_url_after_wait.rstrip('/'):
                is_session_valid = True
            elif INITIAL_URL in current_url_after_wait: # INITIAL_URLがサブパスの場合など
                is_session_valid = True
            # ログインページへのリダイレクトの一般的な兆候
            elif not any(keyword in current_url_after_wait.lower() for keyword in ["login", "signin", "authenticate", "consent", "auth/realms"]):
                # より柔軟な判定: ログインページっぽくなければセッション有効と判断
                logger.info(f"URLはINITIAL_URLと異なりますが、ログインページではなさそうです。セッション有効と判断します。")
                is_session_valid = True

            if is_session_valid:
                logger.info("✓ セッション有効。ログイン状態が維持されています。")
                # 成功時には新しいCookieを保存する
                new_cookies = driver.get_cookies()
                if new_cookies and len(new_cookies) >= len(saved_cookies):
                    logger.info("新しいCookieが見つかりました。ファイルを更新します。")
                    saved_cookies = new_cookies
                    save_cookies_to_file(saved_cookies)

                # LocalStorageとSessionStorageも更新
                save_local_storage(driver)

                logger.info("ブラウザを閉じて次のループへ進みます。")
                driver.quit()
                driver = None
            else:
                logger.error(f"セッション切れ。現在のURL ({current_url_after_wait}) がINITIAL_URL ({INITIAL_URL}) と異なります。")
                logger.error("ログインページにリダイレクトされたと判断し、処理を終了します。")
                if driver:
                    driver.quit()
                    driver = None
                break  # ループを終了

    except KeyboardInterrupt:
        logger.info("ユーザーにより処理が中断されました。")
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}", exc_info=True)
    finally:
        if driver:
            logger.info("最終処理としてブラウザを閉じます。")
            driver.quit()
        logger.info("セッション有効性チェックツールを終了します。")

if __name__ == "__main__":
    main()
