from django.contrib import admin
from .models import Config, User, Line, Log, Slot, PayCard, Payment
from django.forms import ModelForm
from django.core.exceptions import ValidationError
from datetime import datetime, timezone
from .lib import hkmethod
from import_export.admin import ExportActionMixin
from django.utils.html import format_html
from django.contrib import messages
from django.utils import timezone
import time, json


hkmethod.setBase(Config.objects.get(key='BASE_URL').value, Config.objects.get(key='API_VERSION').value)

# Register your models here.
class ConfigAdmin(admin.ModelAdmin):
    fields = ['key', 'value', 'comment']
    list_display = ('key', 'value', 'comment', 'updated_at')

class UserForm(ModelForm):
    class Meta:
        model = User
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        if self.instance.sort_date:
            self.initial['sort_date'] = "\r\n".join(self.instance.sort_date.split(','))

    # Add validation
    def clean(self):
        cleaned_data = super().clean()

        # If start with !, skip verify
        if cleaned_data.get('loginInfo')[0] == '!':
            cleaned_data['loginInfo'] = cleaned_data.get('loginInfo')[1:]
            return cleaned_data

        # Validate new add not start with '#'; Validate change from '#'
        if (len(self.initial) == 0 and cleaned_data.get('loginInfo')[0] != '#') or \
            (len(self.initial) != 0 and self.initial['loginInfo'][0] == '#' and cleaned_data.get('loginInfo')[0] != '#'):
            try:
                print('validate...')
                email, pwd = cleaned_data.get('loginInfo').split(',')
                ret = hkmethod.login(email, pwd, debug=False)
            except Exception as e:
                raise ValidationError('Login failed. %s' % str(e))
            # #  save token, update status
            # if cleaned_data.get('status') == 'processing':
            #     # Cookie field not in the form, use this method to update
            #     self.instance.cookie = 'fakecookie,' + ret['token'] + ',' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            #     # Status field in the form, can change the cleaned_data
            #     cleaned_data['status'] = 'login'
            #     return cleaned_data

@admin.action(description='Paid')
def paid_action(modeladmin, request, queryset):
    count = 0
    for obj in queryset:
        if obj.status in ['payment', 'booked']:
            obj.status = 'checking'
            obj.save()
            count += 1
    modeladmin.message_user(request, 'You marked %i orders as paid. Going to check order status.'%count, messages.SUCCESS)

@admin.action(description='Paid->Done')
def done_action(modeladmin, request, queryset):
    count = 0
    for obj in queryset:
        if obj.status in ['paid']:
            obj.status = 'done'
            obj.save()
            count += 1
    modeladmin.message_user(request, 'You marked %i orders as Done.'%count, messages.SUCCESS)

@admin.action(description='Pending->Processing')
def status_processing_action(modeladmin, request, queryset):
    count = 0
    for obj in queryset:
        if obj.status in ['pending']:
            obj.status = 'processing'
            obj.save()
            count += 1
    modeladmin.message_user(request, 'You moved %i orders to Processing.' % count, messages.SUCCESS)
    
@admin.action(description='*->Pending')
def status_pending_action(modeladmin, request, queryset):
    count = 0
    for obj in queryset:
        if obj.status in ['processing', 'login', 'booked', 'payment', 'checking']:
            obj.status = 'pending'
            obj.save()
            count += 1
    modeladmin.message_user(request, 'You moved %i orders to pending.' % count, messages.SUCCESS)

# @admin.action(description='Force Book!')
# def force_book_action(modeladmin, request, queryset):
#     msg = ''
#     for obj in queryset:
#         if obj.status != 'login':
#             modeladmin.message_user(request, 'Only login user can try force book!', messages.ERROR)
#             return
#         if obj.bookDate is None:
#             modeladmin.message_user(request, 'Please set the book date in bookDate field!', messages.ERROR)
#             return
#         retry = int(Config.objects.get(key='FORCE_BOOK_RETRY').value)
#         cookie, token, createdAt = obj.cookie.split(',')
#         passengerInfo = obj.passengerInfo.split(',')
#         passengers = []
#         for k in range(int(len(passengerInfo) / 2)):
#             passengers.append({'id': passengerInfo[k * 2], 'name': passengerInfo[1 + k * 2]})
#         to_tz = timezone.get_default_timezone()
#         ret = ''
#         print('User #%i: Try to book '% obj.id, obj.bookDate.strftime('%Y-%m-%d'), obj.bookDate.astimezone(to_tz).strftime('%H:%M:%S'))
#         for i in range(retry):
#             try:
#                 order = hkmethod.book(obj.bookDate.strftime('%Y-%m-%d'), obj.bookDate.astimezone(to_tz).strftime('%H:%M:%S'), passengers, token, obj.line.key)
#             except Exception as e:
#                 ret = '#%i Failed: %s; ' % (obj.id, str(e))
#                 time.sleep(float(Config.objects.get(key='FORCE_BOOK_STEP').value))
#                 continue
#             print('SUCCESS!!! Order #', order)
#             ret = '#%i success: %s; '%(obj.id, order)
#             obj.bookNumber = order
#             obj.status = 'booked'
#             obj.save()
#             break
#             # payment link will be generated by check script...
#         msg += ret
#     modeladmin.message_user(request, msg, messages.SUCCESS)

@admin.action(description='Search orders')
def check_collect_action(modeladmin, request, queryset):
    msg = ''
    for obj in queryset:
        if (obj.cookie is None) or (len(obj.cookie) < 3):
            msg += 'User #%i cookie is invalid; '%obj.id
            continue
        cookie = json.loads(obj.cookie)
        try:
            unpaid_order = hkmethod.getOrders(0, cookie)
            paid_order = hkmethod.getOrders(1, cookie)
        except Exception as e:
            msg += 'User #%i search order failed: %s; ' % (obj.id, str(e))
            continue
        Log.objects.create(code='INFO',
                           msg='User #%i has %i paid orders: %s; %i unpaid orders: %s '% (obj.id, len(paid_order), str(paid_order), len(unpaid_order), str(unpaid_order)))
        msg += 'User #%i has %i/%i orders; '% (obj.id, len(paid_order), len(paid_order) + len(unpaid_order))
    modeladmin.message_user(request, msg, messages.SUCCESS)

def reset_action(modeladmin, request, queryset):
    queryset.update(cookie=None, bookNumber=None, bookDate=None, runningNode="")
    modeladmin.message_user(request, 'You have reset %i orders.' % len(queryset), messages.SUCCESS)

class UserAdmin(ExportActionMixin, admin.ModelAdmin):
    list_display = (
        'id', 'success', 'payment_link', 'show_status', 'linkComment', 'paidAt', 'loginInfo', 'priority', 'price', 'comment',
        'updatedAt', 'bookDate', 'runningNode', 'passengerCount', 'ticket_price', 'line', 'createdAt')
    list_filter = ('status', 'line')
    fieldsets = [
        ('Login Info.', {'fields': ['line', 'loginInfo', 'passengerInfo', 'sort_date', 'allow_today']}),
        ('Sales Info.', {'fields': ['linkComment', 'comment', 'price', 'priority']}),
        ('Result', {'fields': ['cookie', 'runningNode', 'bookNumber', 'bookDate', 'status', 'added_by']}),
    ]

    @admin.display(description='status')
    def show_status(self, obj):
        status = obj.status
        if status == 'pending':
            return format_html('<span style="color: red; font-weight: bold;">{}</span>', status)
        elif status in ['paid', 'done']:
            return format_html('<span style="color: green;">{}</span>', status)
        elif status == 'payment':
            return format_html('<span style="color: red;">{}</span>', status)
        elif status in ['booked', 'login', 'checking']:
            return format_html('<span style="color: blue;">{}</span>', status)
        elif status == 'canceled' :
            return format_html('<span style="color: grey;">{}</span>', status)
        else:
            return format_html('<span>{}</span>', status)

    @admin.display(description='pay')
    def payment_link(self, obj):
        link = obj.payment_link()
        if link == '':
            return ''
        else:
            dt_seconds = (obj.paymentExpireAt - timezone.now()).total_seconds()
            return format_html(
                '<a href="{}" target="_blank">{}</a> E:{}"{}\'',
                link,
                'click',
                int(dt_seconds / 60),
                abs(int(dt_seconds - int(dt_seconds / 60)*60))
            )

    form = UserForm
    for exportAction in ExportActionMixin.actions:
        exportAction.allowed_permissions = ['operation']
    actions = ExportActionMixin.actions + [
        reset_action,
        # force_book_action,
        check_collect_action,
        status_processing_action,
        status_pending_action,
        paid_action,
        done_action
    ]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.added_by = request.user
        return super().save_model(request, obj, form, change)

    def has_operation_permission(self, request):
        return True

class LogAdmin(ExportActionMixin, admin.ModelAdmin):
    fields = ['code', 'msg']
    list_filter = ('code',)
    list_display = ('id', 'code', 'short_msg', 'updated_at')
    actions = ExportActionMixin.actions

    def has_operation_permission(self, request):
        return True

class PaymentAdmin(ExportActionMixin, admin.ModelAdmin):
    # fields = ['code', 'msg']
    list_filter = ('card__card_info', 'bank_confirm', 'payAt')
    list_display = ('id', 'payAt', 'card', 'amount', 'user_id', 'comment', 'bank_confirm', 'createdAt', 'updatedAt')
    actions = ExportActionMixin.actions

    for exportAction in ExportActionMixin.actions:
        exportAction.allowed_permissions = ['operation']
    actions = ExportActionMixin.actions + [
        'confirm_action',
        'unconfirm_action',
    ]

    @admin.action(description='Confirm')
    def confirm_action(self, request, queryset):
        queryset.update(bank_confirm=True)
        self.message_user(request, 'You have set %i payments to Confirm.' % len(queryset), messages.SUCCESS)

    @admin.action(description='Unconfirm')
    def unconfirm_action(self, request, queryset):
        queryset.update(bank_confirm=False)
        self.message_user(request, 'You have set %i payments to Unconfirm.' % len(queryset), messages.SUCCESS)

    def has_operation_permission(self, request):
        return True

class SlotAdmin(ExportActionMixin, admin.ModelAdmin):
    # fields = ['', 'msg']
    list_display = ('id', 'date', 'time', 'linecode', 'availablePeople', 'maxPeople', 'totalPeople', 'saleStatus')
    list_filter = ('saleStatus', 'linecode')
    actions = ExportActionMixin.actions

    def has_operation_permission(self, request):
        return True

admin.site.site_header = 'HKZH Admin'
admin.site.register(Config, ConfigAdmin)
admin.site.register(User, UserAdmin)
admin.site.register(Line)
admin.site.register(PayCard)
admin.site.register(Payment, PaymentAdmin)
admin.site.register(Log, LogAdmin)
admin.site.register(Slot, SlotAdmin)
