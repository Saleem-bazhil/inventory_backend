import math

from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Customer
from .serializers import CustomerSerializer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _paginate(queryset, request):
    """
    Apply page-based pagination and return (items_qs, meta_dict).
    Query params: page (default 1), per_page (default 20).
    """
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = max(1, min(100, int(request.query_params.get("per_page", 20))))
    except (ValueError, TypeError):
        per_page = 20

    total = queryset.count()
    pages = max(1, math.ceil(total / per_page))
    page = min(page, pages)

    start = (page - 1) * per_page
    items_qs = queryset[start: start + per_page]

    meta = {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }
    return items_qs, meta


# ---------------------------------------------------------------------------
# Customer List + Create
# ---------------------------------------------------------------------------

class CustomerListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Customer.objects.all()

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
                | Q(company__icontains=search)
            )

        qs = qs.order_by("-created_at")

        items_qs, meta = _paginate(qs, request)
        serializer = CustomerSerializer(items_qs, many=True)
        return Response({"items": serializer.data, **meta})

    def post(self, request):
        serializer = CustomerSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Customer Detail (GET / PUT / DELETE)
# ---------------------------------------------------------------------------

class CustomerDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_customer(self, pk):
        try:
            return Customer.objects.get(pk=pk)
        except Customer.DoesNotExist:
            return None

    def get(self, request, pk):
        customer = self._get_customer(pk)
        if customer is None:
            return Response(
                {"detail": "Customer not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(CustomerSerializer(customer).data)

    def put(self, request, pk):
        customer = self._get_customer(pk)
        if customer is None:
            return Response(
                {"detail": "Customer not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = CustomerSerializer(customer, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        customer = self._get_customer(pk)
        if customer is None:
            return Response(
                {"detail": "Customer not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        customer.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
