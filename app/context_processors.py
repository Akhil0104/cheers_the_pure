from .account_utils import detect_account_type


def account_context(request):
    account_type = None
    company_name = ''
    if request.user.is_authenticated:
        profile = getattr(request.user, 'profile', None)
        if profile:
            account_type = profile.account_type
            company_name = profile.company_name
        else:
            account_type = detect_account_type(request.user.email)
    return {
        'user_account_type': account_type,
        'user_company_name': company_name,
        'is_b2c_user': account_type == 'b2c',
        'is_b2b_user': account_type == 'b2b',
    }
