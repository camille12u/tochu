import logging

from allauth.account.internal.flows.email_verification import (
    get_address_for_login,
    send_verification_email_to_address,
    )
from allauth.account.models import EmailAddress
from allauth.account.stages import (
    LoginStageController, 
    EmailVerificationStage,
    )
from allauth.account.views import EmailVerificationSentView
from django.contrib import messages
from django.shortcuts import redirect
from django.views.generic import View


logger = logging.getLogger(__name__)


class ResendingEmailView(View):
    """メール再送処理を扱うクラス"""
    def post(self, request, *args, **kwargs):
        # ログイン済みかつメール確認済みで直接再送URLへPOST
        if request.user.is_authenticated:
            if EmailAddress.objects.filter(
                user=request.user, verified=True
                ).exists():
                return redirect('/learning/')

        # 同じブラウザに保持された、有効なメール確認待ちの手続きを取得する
        key = EmailVerificationStage.key
        verification_stage = LoginStageController.enter(request, stage_key=key)

        # 途中情報がない・期限切れなどの場合は、ログインからやり直す
        if verification_stage is None:
            messages.warning(
                request, 
                '確認手続きを続けられませんでした。もう一度ログインしてください。'
                )
            logger.warning(
                '「メール確認待ちのログイン途中情報がない、'
                'または期限切れのため再送処理が完了しませんでした」'
                )
            return redirect('account_login')

        # 有効な途中情報あるが、対象ユーザーを取得できない場合再送処理せず、トップページに遷移
        elif verification_stage and verification_stage.login.user is None:
            messages.warning(
                request, 
                '確認手続きを続けられませんでした。ログイン、または会員登録からやり直してください'
                )
            return redirect('top')
    
        else: 
            # 有効な手続きと対象ユーザーを取得できた
            # メール確認待ちの手続きに対応するEmailAddressを取得する
            emali_object = get_address_for_login(verification_stage.login)

            # 対象のメール情報がない
            if emali_object is None:
                messages.warning(
                    request, '確認手続きを続けられませんでした。もう一度ログインしてください。'
                )
                return redirect('account_login')

            # 対象のメール情報があり、既に確認済み
            elif emali_object.verified:
                messages.info(
                    request, 'メールアドレスの確認はすでに完了しています。'
                )
                return redirect('account_login')
            
            else: # 対象のメールアドレス情報があり、かつ確認メール未確認

                # 送信制限を確認し、送信可能なら確認メールを再送する
                email_sent = send_verification_email_to_address(
                    request, 
                    emali_object,
                    verification_stage.login.signup
                    )
                
                if email_sent:
                    # 再送に成功した場合は、成功ログを記録して案内画面へ戻す
                    logger.info('「確認メールの再送処理が完了しました」')
                    return redirect('account_email_verification_sent')

                # 送信制限で再送できなかった場合は、利用者へ案内を表示する
                messages.warning(
                    request,
                    '続けて再送することはできません。しばらく待ってから、もう一度お試しください。'
                    )
                
                return redirect('account_email_verification_sent')


class TochuEmailVerificationSentView(EmailVerificationSentView):
    """TOCHU用の、確認メール送信済み案内画面を扱うView"""
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            # ログインユーザーのメールがある、かつそのメールが確認済みを検索し
            # それらが存在するか判定
            if EmailAddress.objects.filter(user=request.user, verified=True).exists():
                return redirect('/learning/') # 学習記録一覧へ遷移

        return super().get(request)
