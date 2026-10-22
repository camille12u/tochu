from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import View
from allauth.account.internal.flows.email_verification import (
    get_address_for_login,
    send_verification_email_to_address,
    )
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
    
        else: # 有効な手続きと対象ユーザーを取得できた
            # メール確認待ちの手続きに対応するEmailAddressを取得する
            # 取得できない場合はNoneが返る
            emali_object = get_address_for_login(verification_stage.login)

            if emali_object is None:
                return redirect('account_login') # 対象のメール情報がない

            elif emali_object.verified:
                return redirect('account_login') # 対象のメール情報があり、既に確認済み
            
            else: # 対象のメール情報があり、かつメール未確認
                result = send_verification_email_to_address(
                    request, emali_object,
                    verification_stage.login.signup
                    )
                
                # 送信制限を確認
                if not result:
                    messages.warning(
                        request,
                        '続けて再送することはできません。しばらく待ってから、もう一度お試しください。'
                        )

                # メール認証送信済み画面へ遷移
                return redirect('account_email_verification_sent') 