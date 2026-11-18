from rest_framework import serializers

from apps.common.tenancy import TenantViewSet

from .models import Expense


class ExpenseSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Expense
        fields = ["id", "category", "category_label", "amount", "spent_on", "note", "created_at"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value


class ExpenseViewSet(TenantViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    owner_only = True
    filter_backends = []

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("from"):
            qs = qs.filter(spent_on__gte=params["from"])
        if params.get("to"):
            qs = qs.filter(spent_on__lte=params["to"])
        if params.get("category"):
            qs = qs.filter(category=params["category"])
        return qs

    def perform_create(self, serializer):
        serializer.save(turf=self.request.tenant, created_by=self.request.user)
