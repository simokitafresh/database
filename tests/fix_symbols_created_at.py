#!/usr/bin/env python3
"""
Fix script for the symbols table created_at column issue.

This script provides instructions for fixing the database schema issue.
"""

print("""
=== 解決方法: symbols テーブルに created_at カラムを追加 ===

問題：
- auto_register.py が symbols テーブルに存在しない created_at カラムを使用しようとしている
- これによりシンボル自動登録が失敗している

解決策：
1. 新しいマイグレーションファイルが作成されました: 007_add_created_at_to_symbols.py
2. Symbol モデルに created_at カラムが追加されました
3. 以下のコマンドでマイグレーションを実行してください：

   # データベースが起動していることを確認
   docker-compose up -d db
   
   # マイグレーションを実行
   alembic upgrade head

4. マイグレーション後、auto_register.py は正常に動作します

追加情報：
- created_at カラムには server_default=sa.func.now() が設定されているため、既存レコードも自動的に現在時刻で更新されます
- 新しいシンボルが登録されるときに作成日時が記録されます
- このカラムによりシンボルの登録履歴を追跡できます

マイグレーション実行後、アプリケーションを再起動してテストしてください。
""")
