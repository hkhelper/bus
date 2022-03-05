from rest_framework import serializers
from .models import Config, Log, User, Slot


class ConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = Config
        fields = ('key', 'value',)

class LogSerializer(serializers.ModelSerializer):
    class Meta:
        model = Log
        fields = ('id', 'code', 'msg',)

class UserSerializer(serializers.ModelSerializer):
    line_code = serializers.ReadOnlyField(source='line.key')
    class Meta:
        model = User
        fields = ('id', 'line_code', 'loginInfo', 'passengerInfo', 'passengerCount', 'sort_date', 'cookie', 'bookNumber', 'bookDate', 'updatedAt', 'paidAt', 'status', 'runningNode', 'priority', 'comment', 'payment_link', 'price', 'ticket_price', 'paymentExpireAt')

class SlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Slot
        fields = ('id', 'date', 'time', 'linecode', 'maxPeople', 'totalPeople', 'availablePeople', 'saleStatus',)