from django.contrib import messages
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Case, IntegerField, Min, Q, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .backup import take_snapshot
from .decorators import page_required
from .models import Operator
from .perms import ROLE_META, set_membership


@page_required('users')
def users(request):
    query = (request.GET.get('q') or '').strip()
    show_off = request.GET.get('off') == '1'
    editing = None
    if request.GET.get('edit'):
        editing = Operator.objects.filter(pk=request.GET['edit']).first()
    role_rank = Coalesce(Min(Case(
        When(groups__name='superadmin', then=Value(0)),
        When(groups__name='manager', then=Value(1)),
        When(groups__name='mentor', then=Value(2)),
        When(groups__name='specialist', then=Value(3)),
        default=Value(9),
        output_field=IntegerField(),
    )), Value(9))
    people = Operator.objects.select_related('mentor').prefetch_related('groups').annotate(role_rank=role_rank).order_by('role_rank', 'full_name')
    if not show_off:
        people = people.filter(is_active=True)
    if query:
        people = people.filter(Q(full_name__icontains=query) | Q(username__icontains=query) | Q(expert_name__icontains=query))
    mentors = Operator.objects.filter(groups__name='mentor', is_active=True)
    tree = []
    for mentor in mentors:
        tree.append({
            'mentor': mentor,
            'members': mentor.mentees.filter(is_active=True),
        })
    return render(request, 'panel/users.html', {
        'people': people,
        'mentors': mentors,
        'editing': editing,
        'query': query,
        'show_off': show_off,
        'tree': tree,
        'role_meta': ROLE_META,
        'open_modal': bool(request.GET.get('new') or editing),
    })


@require_POST
@page_required('users')
def save_user(request):
    username = request.POST.get('username', '').strip()
    original = request.POST.get('original', '').strip()
    full_name = request.POST.get('full_name', '').strip()
    role = request.POST.get('role') or 'specialist'
    finance = request.POST.get('finance') == '1'
    expert_name = request.POST.get('expert_name', '').strip()
    password = request.POST.get('password', '')
    mentor_id = request.POST.get('mentor') or None
    if role not in ROLE_META:
        role = 'specialist'
    if not username or not full_name:
        messages.error(request, 'نام و نام کاربری لازم است.')
        return redirect('users')
    if role in {'specialist', 'mentor'} and not expert_name:
        messages.error(request, 'برای کارشناس و منتور، نام ستون «کارشناس فروش» لازم است.')
        return redirect('users')
    if original:
        user = get_object_or_404(Operator, pk=original)
        if Operator.objects.exclude(pk=user.pk).filter(username=username).exists():
            messages.error(request, 'این نام کاربری قبلاً ثبت شده است.')
            return redirect('users')
    else:
        if Operator.objects.filter(username=username).exists():
            messages.error(request, 'این نام کاربری قبلاً ثبت شده است.')
            return redirect('users')
        if not password:
            messages.error(request, 'برای کاربر جدید رمز عبور لازم است.')
            return redirect('users')
        user = Operator(username=username)
    if password:
        try:
            validate_password(password, user)
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
            return redirect('users')
        user.set_password(password)
    user.username = username
    user.full_name = full_name
    user.expert_name = expert_name
    if role == 'specialist' and mentor_id:
        user.mentor = Operator.objects.filter(pk=mentor_id, groups__name='mentor').first()
    else:
        user.mentor = None
    user.save()
    set_membership(user, role, finance)
    take_snapshot('users')
    messages.success(request, 'حساب ذخیره شد.')
    return redirect('users')


@require_POST
@page_required('users')
def toggle_user(request, pk):
    user = get_object_or_404(Operator, pk=pk)
    if user.pk == request.user.pk:
        messages.error(request, 'نمی‌توانید حساب خودتان را غیرفعال کنید.')
        return redirect('users')
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    take_snapshot('users')
    messages.success(request, 'وضعیت حساب عوض شد.')
    return redirect('users')


@require_POST
@page_required('users')
def delete_user(request, pk):
    user = get_object_or_404(Operator, pk=pk)
    if user.pk == request.user.pk:
        messages.error(request, 'حذف حساب جاری ممکن نیست.')
        return redirect('users')
    if user.role == 'superadmin' and Operator.objects.filter(groups__name='superadmin', is_active=True).count() <= 1:
        messages.error(request, 'آخرین مدیر کل را نمی‌توان حذف کرد.')
        return redirect('users')
    user.delete()
    take_snapshot('users')
    messages.success(request, 'کاربر حذف شد.')
    return redirect('users')
