from django.http import HttpResponse
from django.shortcuts import redirect
from django.views.generic import View
from allauth.account.stages import LoginStageController, EmailVerificationStage


class ResendingEmailView(View):
    def post(self, request, *args, **kwargs):
        # 同じブラウザに保持された、有効なメール確認待ちの手続きを取得する
        key = EmailVerificationStage.key
        verification_stage = LoginStageController.enter(request, stage_key=key)

        # 途中情報がない・期限切れなどの場合は、ログインからやり直す
        if verification_stage is None:
            return redirect('account_login')

        # 手続きがあっても、対象ユーザーがいなければ再送処理には進めない
        elif verification_stage and verification_stage.login.user is None:
            return redirect('account_login')
        else:
            # 有効な手続きと対象ユーザーを取得できた
            # TODO: メールの未確認判定と再送処理を追加する
            return redirect('account_email_verification_sent') # メール認証送信済み画面