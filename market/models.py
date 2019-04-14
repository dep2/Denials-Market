import random
from django.db import models
from django.contrib.auth import get_user_model
from django.db.models.signals import pre_save, post_save
from django.urls import reverse
from decimal import Decimal

User = get_user_model()


TRANSACTION_MODES = (
    ('buy', 'BUY'),
    ('sell', 'SELL')
)

CAP_TYPES = (
    ('small', 'Small Cap'),
    ('mid', 'Mid Cap'),
    ('large', 'Large Cap'),
)


class Company(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=20, unique=True)
    cap = models.DecimalField(max_digits=20, decimal_places=2, default=0.00)
    cmp = models.DecimalField(max_digits=20, decimal_places=2, default=0.00)
    change = models.DecimalField(max_digits=10, decimal_places=2,default=0.00)
    stocks_offered = models.IntegerField(default=0)
    stocks_remaining = models.IntegerField(default=stocks_offered)
    cap_type = models.CharField(max_length=20, choices=CAP_TYPES, blank=True, null=True)
    max_stocks_sell = models.IntegerField(default=100)
    industry = models.CharField(max_length=120, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['cap_type', 'code']

    def __str__(self):
        return self.name

    def get_cap(self):
        cap_type = self.cap_type
        if cap_type=='small':
            return 'Small Cap'
        elif cap_type=='mid':
            return 'Mid Cap'
        return 'Large Cap'

    def get_absolute_url(self):
        return reverse('market:transaction',kwargs={'code':self.code})

    def user_buy_stocks(self, quantity):
        if quantity <= self.stocks_remaining:
            self.stocks_remaining -= quantity
            self.save()
            return True
        return False

    def user_sell_stocks(self, quantity):
        if quantity <= self.stocks_offered:
            self.stocks_remaining += quantity
            self.save()
            return True
        return False

    def calculate_change(self, old_price):
        self.change = ((self.cmp - old_price) / old_price) * Decimal(100.00)
        self.save()

    def update_cmp(self):
        old_price = self.cmp
        temp_stocks_bought = random.randint(100,150)
        temp_stocks_sold = random.randint(100,150)
        self.cmp += (
            self.cmp * Decimal(temp_stocks_bought) - self.cmp * Decimal(temp_stocks_sold)
        ) / Decimal(self.stocks_offered)
        self.calculate_change(old_price)
        self.save()


def pre_save_company_receiver(sender, instance, *args, **kwargs):
    # Setting the maximum stocks that a user can own for a company
    if instance.cap_type == 'small':
        instance.max_stocks_sell = instance.stocks_offered * 0.18
    elif instance.cap_type == 'mid':
        instance.max_stocks_sell = instance.stocks_offered * 0.12
    elif instance.cap_type == 'large':
        instance.max_stocks_sell = instance.stocks_offered * 0.08

    if instance.cmp <= Decimal(0.00):
        instance.cmp = Decimal(0.01)


pre_save.connect(pre_save_company_receiver, sender=Company)


def post_save_company_receiver(sender, instance, created, *args, **kwargs):
    if created:
        user_qs = User.objects.all()
        for user in user_qs:
            obj, create= InvestmentRecord.objects.get_or_create(user=user, company=instance)


post_save.connect(post_save_company_receiver, sender=Company)


class TransactionQueryset(models.query.QuerySet):
    def get_by_user(self, user):
        return self.filter(user=user)

    def get_by_company(self, company):
        return self.filter(company=company)

    def get_by_user_and_company(self, user, company):
        return self.filter(user=user, company=company)


class TransactionManager(models.Manager):
    def get_queryset(self):
        return TransactionQueryset(self.model, using=self._db)

    def get_by_user(self, user):
        return self.get_queryset().get_by_user(user=user)

    def get_by_company(self, company):
        return self.get_queryset().get_by_company(company=company)

    def get_by_user_and_company(self, user, company):
        return self.get_queryset().get_by_user_and_company(user=user, company=company)


class Transaction(models.Model):
    user = models.ForeignKey(User, on_delete=True)
    company = models.ForeignKey(Company, on_delete=True)
    num_stocks = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=20, decimal_places=2, default=0.00)
    mode = models.CharField(max_length=10, choices=TRANSACTION_MODES)
    user_net_worth = models.DecimalField(max_digits=20, decimal_places=2, default=0.00)
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    objects = TransactionManager()

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return '{user}: {company} - {time}'.format(
            user=self.user.username, company=self.company.name, time=self.timestamp
        )


def pre_save_transaction_receiver(sender, instance, *args, **kwargs):
    amount = InvestmentRecord.objects.calculate_net_worth(instance.user)
    instance.user_net_worth = amount

    investment_obj , obj_created = InvestmentRecord.objects.get_or_create(user=instance.user,
                                                                          company=instance.company)

    if instance.mode == 'buy':
        instance.user.buy_stocks(instance.num_stocks, instance.price)
        instance.company.user_buy_stocks(instance.num_stocks)
        investment_obj.add_stocks(instance.num_stocks)
    elif instance.mode == 'sell':
        instance.user.sell_stocks(instance.num_stocks, instance.price)
        instance.company.user_sell_stocks(instance.num_stocks)
        investment_obj.reduce_stocks(instance.num_stocks)


pre_save.connect(pre_save_transaction_receiver, sender=Transaction)


def post_save_transaction_create_receiver(sender, instance, created, *args, **kwargs):
    if created:
        net_worth_list = [
            instance.user_net_worth for transaction in Transaction.objects.filter(user=instance.user)
        ]

        instance.user.update_cv(net_worth_list)


post_save.connect(post_save_transaction_create_receiver, sender=Transaction)


class InvestmentRecordQueryset(models.query.QuerySet):
    def get_by_user(self, user):
        return self.filter(user=user)

    def get_by_company(self, company):
        return self.filter(company=company)


class InvestmentRecordManager(models.Manager):
    def get_queryset(self):
        return InvestmentRecordQueryset(self.model, self._db)

    def get_by_user(self, user):
        return self.get_queryset().get_by_user(user=user)

    def get_by_company(self, company):
        return self.get_queryset().get_by_company(company=company)

    def calculate_net_worth(self, user):
        qs = self.get_by_user(user)
        amount = Decimal(0.00)
        for inv in qs:
            amount += Decimal(inv.stocks) * inv.company.cmp
        return amount + user.cash


class InvestmentRecord(models.Model):
    user = models.ForeignKey(User, on_delete=True)
    company = models.ForeignKey(Company, on_delete=True)
    stocks = models.IntegerField(default=0)
    updated = models.DateTimeField(auto_now=True)

    objects = InvestmentRecordManager()

    class Meta:
        unique_together = ('user', 'company')

    def __str__(self):
        return self.user.username + ' - ' + self.company.code

    def add_stocks(self, num_stocks):
        self.stocks += num_stocks
        self.save()

    def reduce_stocks(self, num_stocks):
        if self.stocks >= num_stocks:
            self.stocks -= num_stocks
            self.save()


def post_save_user_create_receiver(sender, instance, created, *args, **kwargs):
    '''For every user created'''
    if created:
        '''It will create user's investment record with all the companies'''
        for company in Company.objects.all():
            obj = InvestmentRecord.objects.create(user=instance, company=company)


post_save.connect(post_save_user_create_receiver, sender=User)


class CompanyCMPRecord(models.Model):
    company = models.ForeignKey(Company, on_delete=True)
    cmp = models.DecimalField(max_digits=20, decimal_places=2, default=0.00)
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return self.company.code

