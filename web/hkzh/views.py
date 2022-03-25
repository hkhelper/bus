
# Create your views here.
from .models import Config, User, Log, Line, Slot
from django.shortcuts import render, redirect
from django.http import HttpResponse
from rest_framework import generics, response, viewsets
from .serializers import ConfigSerializer, LogSerializer, UserSerializer, SlotSerializer
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Q
from django.db import transaction
import operator
from .lib import hkmethod
from functools import reduce
import dateutil.relativedelta
from django.utils import timezone

@transaction.atomic
def filterUserIdBySchedule(node='Unknown'):
    schedule_dates = Config.objects.get(key='SCHEDULE_CHECK_DATE').value.split(',')
    updateTime_minutes = int(Config.objects.get(key='SCHEDULE_RUN_MAX_MINUTE').value)
    updateTime = timezone.now() - dateutil.relativedelta.relativedelta(minutes=updateTime_minutes)
    # Use select_for_update() to lock these row.
    q = User.objects.select_for_update().filter(status__in=['processing', 'login', 'booked', 'payment', 'checking'])\
        .filter(reduce(operator.or_, (Q(sort_date__contains=date) for date in schedule_dates)))\
        .filter(Q(runningNode='') | (~Q(runningNode='') & Q(updatedAt__lte=updateTime)))\
        .order_by('-priority', '-price')
    if q.count() == 0:
        return 0
    select = q.first()
    select.runningNode = node
    select.save()
    return select.id

def filterUserIdByDate(lineCode, date, availableCount):
    try:
        lineid = Line.objects.get(key=lineCode).id
    except Exception as e:
        print(e)
        raise ValueError('Line code not found. ')
    q = User.objects.filter(line=lineid, status='login', cookie__isnull=False, cookie__gt='',
                            passengerCount__lte=availableCount, sort_date__contains=date)
    if date == timezone.now().strftime('%Y-%m-%d'):
        q = q.filter(allow_today=True)
    q = q.order_by('-passengerCount', '-priority', '-price')
    if q.count() == 0:
        return 0
    return q.first().id

def filterSlotUser():
    q = User.objects.filter(use_slot=True).order_by('-id')
    if q.count() == 0:
        raise ValueError('No slot user set.')
    return q.first().id

def isDebugMode():
    return bool(Config.objects.get(key='debugMode').value)

@login_required
def index(request):
    return render(request, 'hkzh/index.html', getJsonData(request))

@login_required
def pay(request, pk):
    bookNumber = User.objects.get(id=pk).bookNumber
    if (bookNumber is None) or (bookNumber == ''):
        return HttpResponse('bookNumber is Empty.')
    bookNumber = bookNumber.split(',')
    if len(bookNumber) != 3:
        return HttpResponse('bookNumber does not include the session...')
    session = bookNumber[-1]
    link = hkmethod.redirectPayment(session)
    return render(request, 'hkzh/pay.html', {'userId': pk, 'link': link})

class ConfigList(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = Config.objects.all()
    serializer_class = ConfigSerializer

class ConfigGet(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = Config.objects.all()
    serializer_class = ConfigSerializer

class ConfigUpdate(generics.UpdateAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = Config.objects.all()
    serializer_class = ConfigSerializer
    lookup_field = 'pk'

    def update(self, request, *args, **kwargs):
        key = kwargs['pk']
        Log.objects.create(code='Update', msg='Config %s updated: %s' % (key, str(request.data)))
        return super().update(request, *args, **kwargs)

class LogAdd(generics.CreateAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = Log.objects.all()
    serializer_class = LogSerializer
    filter_fields = ('code', 'msg')

class UserGetByStatus(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_queryset(self, status):
        return User.objects.filter(status__in=status.split(','))

    def list(self, request, *args, **kwargs):
        status = kwargs['status']
        # Note the use of `get_queryset()` instead of `self.queryset`
        queryset = self.get_queryset(status)
        serializer = UserSerializer(queryset, many=True)
        return response.Response(serializer.data)

class UserGetSchedule(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_queryset(self, pk):
        return User.objects.filter(pk=pk)

    def list(self, request, *args, **kwargs):
        try:
            id = filterUserIdBySchedule(kwargs['node'])
        except Exception as e:
            return response.Response({'error': str(e)})
        # Note the use of `get_queryset()` instead of `self.queryset`
        queryset = self.get_queryset(id)
        serializer = UserSerializer(queryset, many=True)
        return response.Response(serializer.data)

class UserGetByDate(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_queryset(self, pk):
        return User.objects.filter(pk=pk)

    def list(self, request, *args, **kwargs):
        try:
            id = filterUserIdByDate(kwargs['line'], kwargs['date'], kwargs['count'])
        except Exception as e:
            return response.Response({'error':str(e)})
        Log.objects.create(code='Found-'+kwargs['line'], msg='%i available in %s; Use user #%i' % (int(kwargs['count']), kwargs['date'], id))
        # Note the use of `get_queryset()` instead of `self.queryset`
        queryset = self.get_queryset(id)
        serializer = UserSerializer(queryset, many=True)
        return response.Response(serializer.data)


class UserGetSlot(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_queryset(self, pk):
        return User.objects.filter(pk=pk)

    def list(self, request, *args, **kwargs):
        try:
            id = filterSlotUser()
        except Exception as e:
            return response.Response({'error': str(e)})
        queryset = self.get_queryset(id)
        serializer = UserSerializer(queryset, many=True)
        return response.Response(serializer.data)

class UserGet(generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = User.objects.all()
    serializer_class = UserSerializer
    
    def get(self, request, *args, **kwargs):
        # save to update updatedAt
        User.objects.get(id=kwargs['pk']).save()
        return super().get(request, *args, **kwargs)

class UserUpdate(generics.UpdateAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = User.objects.all()
    serializer_class = UserSerializer
    lookup_field = 'pk'

    def update(self, request, *args, **kwargs):
        id = kwargs['pk']
        Log.objects.create(code='Update', msg='User #%i updated: %s'%(id, str(request.data)))
        #Add warning log if status changed from checking->processing
        if ('status' in request.data) and (request.data['status'] != 'paid'):
            if User.objects.get(id=id).status == 'checking':
                Log.objects.create(code='Warning', msg='User #%i status updated checking->processing' % id)
        return super().update(request, *args, **kwargs)

class SlotGetList(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    queryset = Slot.objects.all()
    serializer_class = SlotSerializer

class SlotUpdateViewSet(viewsets.ModelViewSet):
    queryset = Slot.objects.all()
    serializer_class = SlotSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        ###
        # First we need to iterate over the list o items
        ###

        for single_slot in serializer.validated_data:
            Log.objects.create(code='Found-'+single_slot['linecode'], msg='%i available in %s.' % (int(single_slot['availablePeople']), (single_slot['date'] + ' ' + single_slot['time'])))
            # Try to get proportion from database for selected user
            try:
                slot = Slot.objects.get(linecode=single_slot['linecode'], date=single_slot['date'], time=single_slot['time'])
                slot.maxPeople = single_slot['maxPeople']
                slot.totalPeople = single_slot['totalPeople']
                slot.availablePeople = single_slot['availablePeople']
                slot.saleStatus = single_slot['saleStatus']
                slot.save()
            # If it is not in the model, then we should create it
            except Slot.DoesNotExist:
                slot = Slot(
                    linecode=single_slot['linecode'],
                    date=single_slot['date'],
                    time=single_slot['time'],
                    maxPeople=single_slot['maxPeople'],
                    totalPeople=single_slot['totalPeople'],
                    availablePeople=single_slot['availablePeople'],
                    saleStatus=single_slot['saleStatus'],
                )
                slot.save()
        return response.Response({'SUCCESS': 1})

def getJsonData(request):

    user_total = User.objects.count()
    status_count = User.objects.values('status').order_by('status').annotate(count=Count('status'))
    status_sum_ticket_price = User.objects.values('status').order_by('status').annotate(ticket_price=Sum('ticket_price'))
    status_sum_price = User.objects.values('status').order_by('status').annotate(price=Sum('price'))
    status_sum_passenger = User.objects.values('status').order_by('status').annotate(count=Sum('passengerCount'))
    user_data = {
        'total': user_total,
        'status_count': status_count,
        'status_sum_ticket_price': status_sum_ticket_price,
        'status_sum_price': status_sum_price,
        'status_sum_passenger': status_sum_passenger
    }
    # print(user_data)
    return user_data
