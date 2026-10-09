# TOCHU

## アプリの概要

学んだことと、次にやることを記録し、  
少し間が空いても自分の続きから始められる学習ログです。

## インストール

### 前提条件

- condaがインストールされている
- ターミナルでcondaコマンドが使用できる
- ソースコードを取得し、ターミナルでリポジトリ直下へ移動している

### 開発環境

- `conda 25.1.1`
- `Python 3.14.8`
- `Django 5.2.18`

### 仮想環境作成

```Bash
conda create -n 仮想環境名 python=3.14.8 pip -c conda-forge --override-channels
```

### 仮想環境を有効化
```Bash
conda activate 仮想環境名
```

### パッケージのインストール

```Bash
pip install -r requirements.txt
```

### 環境変数ファイルを作成し、秘密鍵を生成

リポジトリ直下で、見本から`.env`を作る。

```Bash
cp .env.example .env
```

#### 秘密鍵を生成する手順

1. 作成した仮想環境名で仮想環境を有効にする
2. ターミナルで `python` を入力し、対話モードを開く
3. `secrets` をインポートし、`token_urlsafe`に**64**を渡して秘密鍵を生成する
4. 生成された文字列を、`.env`の`DJANGO_SECRET_KEY`の値として保存する
5. 対話モードを終了

#### 作成例  
```Bash
python
>>> import secrets
>>> secrets.token_urlsafe(64)
'秘密鍵の表す文字列が生成される'
>>> quit
```

## 設定の確認と開発サーバーの起動手順

**作成した仮想環境を有効にしてから実行する**

1. リポジトリ直下から`src`へ移動する
2. `manage.py`の`check`で設定を確認する
3. 問題がなければ`runserver`で開発サーバーを起動する
4. ブラウザーを開くURL(`http://127.0.0.1:8000/`)、サーバーを止める操作(`Control＋C`)

操作例  
```Bash
cd src
python manage.py check
python manage.py runserver
```

✳︎現在は初期画面の表示まで確認済みで、DBの初期化はカスタムユーザー作成後に行う。