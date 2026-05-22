import math

from django.db.models import Q
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ticket.models import Ticket
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
        user = request.user
        profile = getattr(user, 'userprofile', None)
        role = profile.role if profile else ''

        # Scoping logic - matching HPStock RMA workflow logic
        if role in ['admin', 'super_admin', 'manager']:
            qs = Ticket.objects.all()
        else:
            user_region = profile.region if profile else ''
            if user_region:
                qs = Ticket.objects.filter(region=user_region)
            else:
                qs = Ticket.objects.filter(
                    Q(created_by=user) | Q(current_assignee=user)
                )

        # Filters
        region = request.query_params.get("region", "").strip()
        if region and region != "all":
            if role not in ['admin', 'super_admin', 'manager']:
                user_region = profile.region if profile else ''
                qs = qs.filter(region=user_region)
            else:
                qs = qs.filter(region=region)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(cust_name__icontains=search)
                | Q(cust_contact__icontains=search)
                | Q(cust_email__icontains=search)
                | Q(ticket_number__icontains=search)
                | Q(form_number__icontains=search)
            )

        is_closed_param = request.query_params.get("is_closed", "").strip().lower()
        if is_closed_param == "true":
            qs = qs.filter(current_status="closed")
        elif is_closed_param == "false":
            qs = qs.exclude(current_status="closed")

        qs = qs.order_by("-created_at")

        items_qs, meta = _paginate(qs, request)
        serializer = CustomerSerializer(items_qs, many=True)
        return Response({"items": serializer.data, **meta})

    def post(self, request):
        serializer = CustomerSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        profile = getattr(user, 'userprofile', None)
        role = profile.role if profile else ''
        
        # Determine region
        region = request.data.get("region")
        if not region or role not in ['admin', 'super_admin', 'manager']:
            region = profile.region if profile else 'vellore'
            
        ticket = serializer.save(
            created_by=user,
            region=region,
            current_status="cso_created"
        )
        return Response(CustomerSerializer(ticket).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Customer Detail (GET / PUT / DELETE)
# ---------------------------------------------------------------------------

class CustomerDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_customer(self, request, pk):
        user = request.user
        profile = getattr(user, 'userprofile', None)
        role = profile.role if profile else ''

        try:
            ticket = Ticket.objects.get(pk=pk)
        except Ticket.DoesNotExist:
            return None

        # Scoping logic - matching HPStock
        if role in ['admin', 'super_admin', 'manager']:
            return ticket
        if profile and profile.region and ticket.region == profile.region:
            return ticket
        if ticket.created_by == user or ticket.current_assignee == user:
            return ticket
        return None

    def get(self, request, pk):
        ticket = self._get_customer(request, pk)
        if ticket is None:
            return Response(
                {"detail": "Customer/Ticket not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(CustomerSerializer(ticket).data)

    def put(self, request, pk):
        ticket = self._get_customer(request, pk)
        if ticket is None:
            return Response(
                {"detail": "Customer/Ticket not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = CustomerSerializer(ticket, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(CustomerSerializer(ticket).data)

    def delete(self, request, pk):
        ticket = self._get_customer(request, pk)
        if ticket is None:
            return Response(
                {"detail": "Customer/Ticket not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        profile = getattr(request.user, 'userprofile', None)
        role = profile.role if profile else ''
        if role not in ['admin', 'super_admin', 'manager']:
            return Response(
                {"detail": "Only admins or managers can delete customer cases."},
                status=status.HTTP_403_FORBIDDEN,
            )
            
        ticket.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
