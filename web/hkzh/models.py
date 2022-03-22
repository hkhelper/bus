from django.db import models
from .lib import hkmethod
from datetime import datetime, timedelta
from django.core.exceptions import ValidationError
from django.utils import timezone

# Create your models here.
class Config(models.Model):
    key = models.CharField(max_length=100, primary_key=True)
    value = models.CharField(max_length=9000, blank=True, default="")
    comment = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key

class Line(models.Model):
    key = models.CharField(max_length=20, unique=True)
    label = models.CharField(max_length=500)

    def __str__(self):
        return self.label

class User(models.Model):
    line = models.ForeignKey(Line, on_delete=models.CASCADE)
    loginInfo = models.CharField(max_length=100, help_text='"email,pwd"; Start with # to skip verify with wrong credentials; Start with ! to force input;')
    passengerInfo = models.CharField(max_length=300, help_text='"adult1_id,adult1_name,#kid1_id,kid1_name,..."; Kids/Seniors ID start with #')
    passengerCount = models.IntegerField(default=0, editable=False)
    sort_date = models.TextField(default="", blank=True, help_text='Each line for one date; Use -- for date range; Use * for all schedule date;')
    linkComment = models.CharField(max_length=200, blank=True, default="")
    allow_today = models.BooleanField(default=False)
    # schedule_book = models.BooleanField(default=False)

    cookie = models.CharField(max_length=5000, blank=True, default=None, null=True)
    bookNumber = models.CharField(max_length=200, blank=True, default=None, null=True)
    bookDate = models.DateTimeField(blank=True, default=None, null=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)
    paidAt = models.DateTimeField(blank=True, default=None, null=True)
    paymentExpireAt = models.DateTimeField(blank=True, default=None, null=True)
    status = models.CharField(max_length=20, default='processing', choices = [
        ('canceled', 'Canceled'),
        ('pending', 'Pending'),

        ('processing', 'Processing'),
        ('login', 'Logged in'),
        ('booked', 'Booked'),
        ('payment', 'Pending Payment'),
        ('checking', 'Checking'),
        ('paid', 'Paid'),

        ('done', 'Done')
    ])


    runningNode = models.CharField(max_length=100, blank=True, default="")
    priority = models.SmallIntegerField(default=1)
    comment = models.CharField(max_length=500, blank=True, default="")
    price = models.FloatField(default=0, blank=True)
    ticket_price = models.FloatField(default=0, blank=True)
    added_by = models.CharField(max_length=20, blank=True, default='')

    def logged(self):
        return self.cookie != None
    logged.boolean = True

    def success(self):
        return self.status in ['paid', 'done']
    success.boolean = True

    def payment_link(self):
        if (self.status not in ['payment', 'checking']) or (self.bookNumber is None):
            return ""
        number = self.bookNumber.split(',')
        if len(number) < 3:
            return ""
        return '/hkzh/pay/'+str(self.id)+'/'
        return 'https://mpgsproxy.hzmbus.com/checkout/lightboxEntry/'+number[2]

    def __str__(self):
        return self.loginInfo

    def clean(self):
        # Change some value
        self.sort_date = self.sort_date.strip()
        if self.sort_date:
            # self.sort_date = ",".join(self.sort_date.split("\r\n"))
            sort_date_list = []
            for row in self.sort_date.split("\r\n"):
                if row.find('--') > 0:
                    start, end = row.split('--')
                    start = datetime.strptime(start, '%Y-%m-%d')
                    delta = datetime.strptime(end, '%Y-%m-%d') - start
                    for i in range(delta.days + 1):
                        sort_date_list.append((start + timedelta(days=i)).strftime('%Y-%m-%d'))
                elif row == '*':
                    for scheduleDate in Config.objects.get(key='SCHEDULE_CHECK_DATE').value.split(','):
                        sort_date_list.append(scheduleDate)
                    break
                else:
                    sort_date_list.append(row)
            self.sort_date = ",".join(sort_date_list)

        self.passengerCount = len(self.passengerInfo.split(',')) / 2
        self.ticket_price = hkmethod.calPrice(self.passengerInfo)

class PayCard(models.Model):
    card_info = models.CharField(max_length=100)

    def __str__(self):
        return self.card_info

class Payment(models.Model):
    card = models.ForeignKey(PayCard, on_delete=models.CASCADE)
    payAt = models.DateTimeField(blank=True, default=None, null=True, help_text='Leave blank to use now')
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)
    user_id = models.IntegerField(default=0)
    amount = models.FloatField(default=0, help_text='Leave 0 to use User\'s ticket price')
    comment = models.CharField(max_length=500, blank=True, default="")
    bank_confirm = models.BooleanField(default=False)

    def __str__(self):
        return str(self.id)

    def clean(self):
        # Change some value
        if self.payAt == None:
            self.payAt = timezone.now()
        if (self.amount == 0) and (self.user_id != 0):
            try:
                user = User.objects.get(id=self.user_id)
            except User.DoesNotExist:
                raise ValidationError('User #%i does not exist.'%self.user_id)
            self.amount = user.ticket_price
            if user.status == 'payment':
                # change status payment -> checking
                user.status = 'checking'
                user.save()


class Log(models.Model):
    # id = models.IntegerField(max_length=10, primary_key=True)
    code = models.CharField(max_length=100)
    msg = models.CharField(max_length=6000, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.code

    @property
    def short_msg(self):
        return self.msg if len(self.msg) < 200 else (self.msg[:197] + '...')

class Slot(models.Model):
    date = models.CharField(max_length=20)
    time = models.CharField(max_length=20)
    linecode = models.CharField(max_length=20)
    maxPeople = models.IntegerField(default=0)
    totalPeople = models.IntegerField(default=0)
    availablePeople = models.IntegerField(default=0)
    saleStatus = models.IntegerField(default=0)

    def __str__(self):
        return self.date
