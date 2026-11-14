from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_GET, require_POST

from accounts.dashboards.helpers import get_user_branch, is_manager
from accounts.services.manager_dashboard_presentation import build_manager_dashboard_presentation
from branches.models import Branch
from payments.models import PaymentAgent
from portal.permissions import role_required
from shop.forms import (
    ShopCounterOrderForm,
    ShopProductForm,
    ShopPublicOrderForm,
    ShopStockAdjustmentForm,
    ShopStockInForm,
    StudentShopPaymentForm,
    StudentRemoteOrderRequestForm,
    StudentRemoteOrderOtpForm,
)
from shop.models import ShopCashPaymentSession, ShopOrder, ShopOrderEmailConfirmation, ShopPayment, ShopProduct, ShopProductImage, ShopSequence, ShopStockMovement
from shop.services.shop_cash_session import manager_shop_sessions_for_agent, verify_agent_and_create_shop_session
from shop.services.shop_service import (
    create_counter_order,
    cancel_student_order,
    create_shop_payment,
    create_student_required_order,
    request_student_cart_order_confirmation,
    request_student_remote_order_confirmation,
    confirm_student_remote_order,
    deliver_order,
    ensure_stock_available,
    get_branch_public_shop_identifier,
    get_recommended_products_for_student,
    get_student_cart,
    get_required_shop_context,
    get_manager_shop_context,
    mark_order_ready,
    next_shop_reference,
    validate_shop_payment,
    update_student_cart,
    notify_shop_promotion_published,
)
from students.models import Student


def _payment_agent_for_branch_manager(user, branch):
    return (
        PaymentAgent.objects
        .select_related("user", "branch")
        .filter(user=user, branch=branch, is_active=True)
        .first()
    )


def manager_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not is_manager(request.user):
            return HttpResponse("Non autorise", status=403)
        branch = get_user_branch(request.user)
        if not branch:
            return HttpResponse("Annexe non trouvee", status=403)
        request.branch = branch
        return view_func(request, *args, **kwargs)

    return login_required(wrapper)


def manager_shop_redirect(request):
    if not request.headers.get("HX-Request"):
        return redirect(f"{reverse('accounts:manager_dashboard')}?section=boutique")
    response = HttpResponse("")
    response["HX-Redirect"] = f"{reverse('accounts:manager_dashboard')}?section=boutique"
    return response


def render_manager_shop_panel(request, *, product_form=None, editing_product=None, stock_form=None, stock_adjustment_form=None, counter_order_form=None, shop_error="", status=200):
    shop_context = get_manager_shop_context(request.branch)
    manager_agent = _payment_agent_for_branch_manager(request.user, request.branch)
    active_shop_cash_sessions = manager_shop_sessions_for_agent(manager_agent, limit=12) if manager_agent else []
    context = {
        **shop_context,
        "branch": request.branch,
        "shop_error": shop_error or shop_context.get("shop_error", ""),
        "shop_product_form": product_form or ShopProductForm(),
        "editing_product": editing_product,
        "shop_product_drawer_title": (
            f"Modifier : {editing_product.name}" if editing_product else "Nouvel article"
        ),
        "shop_stock_form": stock_form or ShopStockInForm(branch=request.branch),
        "shop_stock_adjustment_form": stock_adjustment_form or ShopStockAdjustmentForm(branch=request.branch),
        "shop_counter_order_form": counter_order_form or ShopCounterOrderForm(branch=request.branch),
        "manager_agent": manager_agent,
        "active_shop_cash_sessions": active_shop_cash_sessions,
        "active_shop_cash_sessions_count": len(active_shop_cash_sessions),
        "shop_public_identifier": get_branch_public_shop_identifier(request.branch),
    }
    context["manager_ui"] = build_manager_dashboard_presentation(
        active_section="boutique",
        context=context,
        dashboard_url=reverse("accounts:manager_dashboard"),
        active_subview=(request.POST.get("shop_view") or request.GET.get("view") or "sell"),
    )
    response = render(request, "shop/partials/manager_shop_panel.html", context)
    response.status_code = status
    return response


def resolve_public_shop_branch(identifier):
    normalized = (identifier or "").strip()
    if not normalized:
        return None
    lowered = normalized.lower()
    branches = list(Branch.objects.filter(is_active=True))
    for branch in branches:
        if (branch.slug or "").strip().lower() == lowered:
            return branch
        if (branch.code or "").strip().lower() == lowered:
            return branch
        if slugify(branch.name or "") == lowered:
            return branch
    return None


def resolve_public_shop_student(branch, identifier):
    value = (identifier or "").strip()
    if not value:
        return None
    queryset = (
        Student.objects
        .select_related("user", "inscription__candidature")
        .filter(
            is_active=True,
            inscription__candidature__branch=branch,
            inscription__candidature__is_deleted=False,
            inscription__is_archived=False,
        )
    )
    query = Q(user__username__iexact=value) | Q(matricule__iexact=value)
    if value.isdigit():
        query |= Q(user__id=int(value))
    return queryset.filter(query).first()


@require_GET
def public_shop_home(request):
    if request.user.is_authenticated:
        branch = get_user_branch(request.user)
        identifier = get_branch_public_shop_identifier(branch) if branch else ""
        if identifier:
            return redirect(f"/shop/{identifier}/")
    branch = Branch.objects.filter(is_active=True).order_by("name").first()
    identifier = get_branch_public_shop_identifier(branch) if branch else ""
    if identifier:
        return redirect(f"/shop/{identifier}/")
    return HttpResponse("Aucune annexe boutique disponible.", status=404)


def render_public_shop_catalog(request, *, branch, status=200, form=None, selected_product=None):
    selected_category = (request.GET.get("category") or "").strip()
    products = (
        ShopProduct.objects
        .filter(branch=branch, is_active=True)
        .prefetch_related("programmes", "variants")
        .order_by("-is_required", "category", "name")
    )
    if selected_category:
        products = products.filter(category=selected_category)
    products = list(products)
    categories = [
        {"value": value, "label": label, "count": sum(1 for product in products if product.category == value)}
        for value, label in ShopProduct.CATEGORY_CHOICES
    ]
    response = render(
        request,
        "shop/public_catalog.html",
        {
            "branch": branch,
            "products": products,
            "selected_category": selected_category,
            "categories": categories,
            "has_student_profile": bool(getattr(request.user, "is_authenticated", False) and getattr(request.user, "student_profile", None)),
            "branch_public_identifier": get_branch_public_shop_identifier(branch),
            "public_order_form": form or ShopPublicOrderForm(),
            "public_order_product_id": selected_product.id if selected_product else None,
            "public_order_product": selected_product,
            "order_success_reference": (request.GET.get("ordered") or "").strip(),
            "order_error": (request.GET.get("error") or "").strip(),
            "catalog_stats": {
                "products": len(products),
                "required": sum(1 for product in products if product.is_required),
                "available": sum(1 for product in products if product.current_stock > 0),
                "low_stock": sum(1 for product in products if product.is_low_stock),
            },
        },
    )
    response.status_code = status
    return response


@require_GET
def public_shop_catalog(request, branch_slug):
    branch = resolve_public_shop_branch(branch_slug)
    if not branch:
        raise Http404("Annexe boutique introuvable.")
    return render_public_shop_catalog(request, branch=branch)


@require_POST
def public_shop_product_order(request, branch_slug, pk):
    branch = resolve_public_shop_branch(branch_slug)
    if not branch:
        raise Http404("Annexe boutique introuvable.")
    product = get_object_or_404(ShopProduct, pk=pk, branch=branch, is_active=True)
    form = ShopPublicOrderForm(request.POST)
    if not form.is_valid():
        return render_public_shop_catalog(request, branch=branch, status=400, form=form, selected_product=product)

    student_record = None
    if form.cleaned_data["buyer_type"] == "student":
        student_record = resolve_public_shop_student(branch, form.cleaned_data["student_identifier"])
        if not student_record:
            form.add_error("student_identifier", "Aucun etudiant actif ne correspond a cet identifiant dans cette annexe.")
            return render_public_shop_catalog(request, branch=branch, status=400, form=form, selected_product=product)

    actor = request.user if getattr(request.user, "is_authenticated", False) else None
    try:
        order, _payment = create_counter_order(
            branch=branch,
            product=product,
            quantity=form.cleaned_data["quantity"],
            payment_method=form.cleaned_data["payment_method"],
            created_by=actor,
            student=student_record.user if student_record else None,
            customer_name=form.cleaned_data.get("customer_name", ""),
            customer_email=form.cleaned_data.get("customer_email", ""),
            customer_phone=form.cleaned_data.get("customer_phone", ""),
        )
    except ValidationError as exc:
        form.add_error(None, str(exc))
        return render_public_shop_catalog(request, branch=branch, status=400, form=form, selected_product=product)
    return redirect(f"/shop/{get_branch_public_shop_identifier(branch)}/?ordered={order.reference}")


@login_required
@require_GET
def student_required_modal(request):
    context = get_required_shop_context(request.user)
    if getattr(request, "htmx", None):
        context["show_popup"] = True
    return render(request, "shop/partials/student_required_modal.html", context)


@login_required
@require_POST
def student_create_required_order(request):
    product_ids = request.POST.getlist("product_ids")
    error = None
    if not product_ids:
        error = "Aucun article selectionne."
    else:
        try:
            order = create_student_required_order(request.user, product_ids, created_by=request.user)
        except ValidationError as exc:
            error = str(exc)
        except (AttributeError, TypeError):
            error = "Commande impossible : profil etudiant incomplet (inscription ou branche manquante)."
        else:
            if order:
                if getattr(request, "htmx", None):
                    response = render(
                        request,
                        "shop/partials/student_cart_checkout.html",
                        {"order": order},
                    )
                    response["HX-Trigger"] = '{"toast":{"type":"success","message":"Commande créée. Poursuivez le paiement."}}'
                    return response
                return redirect(f"/shop/student/order/{order.pk}/")
            error = "Aucun article selectionne."

    context = get_required_shop_context(request.user)
    context.update({"show_popup": True, "error": error})
    return render(request, "shop/partials/student_required_modal.html", context, status=400)


@login_required
@role_required("student")
@require_GET
def student_remote_order_modal(request):
    products = {product.pk: product for product in get_recommended_products_for_student(request.user)}
    product = products.get(request.GET.get("product", "") and int(request.GET["product"])) if request.GET.get("product", "").isdigit() else None
    if not product:
        return HttpResponse("Article indisponible.", status=404)
    return render(request, "shop/partials/student_remote_order_modal.html", {"product": product, "order_request_form": StudentRemoteOrderRequestForm(initial={"product_id": product.pk}, branch=product.branch)})


@login_required
@role_required("student")
@require_POST
def student_remote_order_request(request):
    products = {product.pk: product for product in get_recommended_products_for_student(request.user)}
    product_id = request.POST.get("product_id")
    product = products.get(int(product_id)) if str(product_id).isdigit() else None
    form = StudentRemoteOrderRequestForm(request.POST, branch=getattr(product, "branch", None))
    if not form.is_valid():
        return render(request, "shop/partials/student_remote_order_modal.html", {"product": product, "order_request_form": form}, status=400)
    try:
        confirmation, product = request_student_remote_order_confirmation(student=request.user, product_id=form.cleaned_data["product_id"], quantity=form.cleaned_data["quantity"], agent_id=form.cleaned_data["agent"].pk)
    except ValidationError as exc:
        form.add_error(None, exc)
        return render(request, "shop/partials/student_remote_order_modal.html", {"product": product, "order_request_form": form}, status=400)
    return render(request, "shop/partials/student_remote_order_otp.html", {"product": product, "quantity": confirmation.quantity, "order_otp_form": StudentRemoteOrderOtpForm(initial={"confirmation_id": confirmation.pk})})


@login_required
@role_required("student")
@require_POST
def student_remote_order_confirm(request):
    form = StudentRemoteOrderOtpForm(request.POST)
    if not form.is_valid():
        return _render_student_order_otp(request, form, status=400)
    try:
        order = confirm_student_remote_order(student=request.user, confirmation_id=form.cleaned_data["confirmation_id"], code=form.cleaned_data["otp_code"])
    except ValidationError as exc:
        form.add_error(None, exc)
        return _render_student_order_otp(request, form, status=400)
    if getattr(order.email_confirmation, "source_cart_id", None):
        return render(request, "shop/partials/student_cart_order_success.html", {"order": order})
    return render(request, "shop/partials/student_remote_order_success.html", {"order": order})


def _mask_email(email):
    local, separator, domain = (email or "").partition("@")
    if not separator:
        return "votre adresse e-mail"
    return f"{local[:1]}***@{domain}"


def _render_student_order_otp(request, form, *, status):
    confirmation_id = form.data.get("confirmation_id") or form.initial.get("confirmation_id")
    confirmation = (
        ShopOrderEmailConfirmation.objects.select_related("agent__user", "source_cart")
        .filter(pk=confirmation_id, student=request.user)
        .first()
        if str(confirmation_id).isdigit()
        else None
    )
    if confirmation and confirmation.source_cart_id:
        return render(
            request,
            "shop/partials/student_cart_otp.html",
            {
                "cart": confirmation.source_cart,
                "confirmation": confirmation,
                "order_otp_form": form,
                "masked_email": _mask_email(request.user.email),
            },
            status=status,
        )
    return render(request, "shop/partials/student_remote_order_otp.html", {"order_otp_form": form}, status=status)


def _render_student_cart(request, *, error="", status=200, order_request_form=None):
    cart = get_student_cart(request.user)
    response = render(
        request,
        "shop/partials/student_cart.html",
        {
            "cart": cart,
            "cart_error": error,
            "order_request_form": order_request_form or StudentRemoteOrderRequestForm(
                branch=getattr(cart, "branch", None),
            ),
        },
    )
    response.status_code = status
    return response


@login_required
@role_required("student")
@require_GET
def student_product_detail(request, pk):
    products = {item.pk: item for item in get_recommended_products_for_student(request.user)}
    product = products.get(pk)
    if not product:
        raise Http404("Article indisponible.")
    return render(
        request,
        "shop/partials/student_product_drawer.html",
        {"product": product, "open": True},
    )


@login_required
@role_required("student")
@require_POST
def student_cart_update(request):
    try:
        cart = update_student_cart(
            user=request.user,
            product_id=request.POST.get("product_id"),
            quantity=request.POST.get("quantity"),
            variant_id=request.POST.get("variant_id") or None,
        )
    except ValidationError as exc:
        return _render_student_cart(request, error=" ".join(exc.messages), status=400)
    response = _render_student_cart(request)
    response["HX-Trigger"] = '{"toast":{"type":"success","message":"Panier mis à jour."}}'
    return response


@login_required
@role_required("student")
@require_POST
def student_cart_checkout(request):
    cart = get_student_cart(request.user)
    form = StudentRemoteOrderRequestForm(
        request.POST,
        branch=getattr(cart, "branch", None),
    )
    if not form.is_valid():
        return _render_student_cart(
            request,
            error="Choisissez un agent de votre annexe.",
            status=400,
            order_request_form=form,
        )
    try:
        confirmation, cart = request_student_cart_order_confirmation(
            student=request.user,
            agent_id=form.cleaned_data["agent"].pk,
        )
    except ValidationError as exc:
        return _render_student_cart(request, error=" ".join(exc.messages), status=400)
    response = render(
        request,
        "shop/partials/student_cart_otp.html",
        {
            "cart": cart,
            "confirmation": confirmation,
            "order_otp_form": StudentRemoteOrderOtpForm(initial={"confirmation_id": confirmation.pk}),
            "masked_email": _mask_email(request.user.email),
        },
    )
    response["HX-Trigger"] = '{"toast":{"type":"success","message":"Code transmis a votre adresse e-mail."}}'
    return response


@login_required
@require_GET
def student_order_detail(request, pk):
    order = get_object_or_404(
        ShopOrder.objects.prefetch_related("items", "items__product", "items__variant", "payments"),
        pk=pk,
        student=request.user,
    )
    balance = order.balance
    is_remote_email_order = ShopOrderEmailConfirmation.objects.filter(order=order).exists()
    payment_form = StudentShopPaymentForm(order=order)
    context = {
        "order": order,
        "payment_form": payment_form,
        "order_balance": balance,
        "has_pending_payment": order.payments.filter(status=ShopPayment.STATUS_PENDING).exists(),
        "can_student_request_payment": not is_remote_email_order,
        "can_student_cancel": (
            order.status in {ShopOrder.STATUS_DRAFT, ShopOrder.STATUS_PENDING_PAYMENT}
            and not order.payments.filter(status=ShopPayment.STATUS_VALIDATED).exists()
            and not order.stock_movements.filter(movement_type=ShopStockMovement.TYPE_OUT).exists()
        ),
    }
    if getattr(request, "htmx", None):
        return render(request, "shop/partials/student_order_detail.html", context)
    return render(request, "shop/student_order_detail.html", context)


@login_required
@require_POST
def student_order_cancel(request, pk):
    order = get_object_or_404(ShopOrder, pk=pk, student=request.user)
    try:
        order = cancel_student_order(order, student=request.user)
    except ValidationError as exc:
        order = ShopOrder.objects.prefetch_related("items", "items__product", "items__variant", "payments").get(pk=order.pk)
        context = {
            "order": order,
            "payment_form": StudentShopPaymentForm(order=order),
            "order_balance": order.balance,
            "has_pending_payment": order.payments.filter(status=ShopPayment.STATUS_PENDING).exists(),
            "can_student_request_payment": not ShopOrderEmailConfirmation.objects.filter(order=order).exists(),
            "can_student_cancel": False,
            "order_error": exc.messages[0] if exc.messages else "Annulation impossible.",
        }
        return render(request, "shop/partials/student_order_detail.html", context, status=400)

    context = {
        "order": order,
        "payment_form": StudentShopPaymentForm(order=order),
        "order_balance": order.balance,
        "has_pending_payment": False,
        "can_student_request_payment": False,
        "can_student_cancel": False,
        "order_success": "Commande annulée. Aucun paiement encaissé ni sortie de stock n’a été modifié.",
    }
    response = render(request, "shop/partials/student_order_detail.html", context)
    response["HX-Trigger"] = '{"toast":{"type":"success","message":"Commande annulée."}}'
    return response


@login_required
@require_POST
def student_order_pay(request, pk):
    order = get_object_or_404(ShopOrder, pk=pk, student=request.user)
    if ShopOrderEmailConfirmation.objects.filter(order=order).exists():
        return HttpResponse("Cette commande est a encaisser par la gestionnaire de l'annexe.", status=403)
    form = StudentShopPaymentForm(request.POST, order=order)
    if not form.is_valid():
        return render(
            request,
            "shop/partials/student_order_detail.html",
            {
                "order": order,
                "payment_form": form,
                "order_balance": order.balance,
                "has_pending_payment": order.payments.filter(status=ShopPayment.STATUS_PENDING).exists(),
            },
            status=400,
        )
    if order.payments.filter(status=ShopPayment.STATUS_PENDING).exists():
        return redirect(f"/shop/student/order/{order.pk}/")
    method = form.cleaned_data["method"]
    amount = form.cleaned_data["amount"]
    auto_validate = False
    payment = create_shop_payment(
        order,
        amount,
        method,
        request.user,
        auto_validate=auto_validate,
        agent=getattr(form, "agent", None),
        cash_session=getattr(form, "cash_session", None),
    )
    order.status = ShopOrder.STATUS_PENDING_PAYMENT
    order.save(update_fields=["status", "updated_at"])
    return redirect(f"/shop/student/order/{order.pk}/")


@login_required
@require_POST
def student_shop_verify_agent(request, pk):
    """HTMX — verification agent avant paiement boutique (blur sur le champ nom)."""

    order = get_object_or_404(ShopOrder, pk=pk, student=request.user)
    if ShopOrderEmailConfirmation.objects.filter(order=order).exists():
        return HttpResponse("Cette commande est a encaisser par la gestionnaire de l'annexe.", status=403)
    agent_name = (request.POST.get("agent_name") or "").strip()
    if not agent_name or len(agent_name) < 2:
        return render(
            request,
            "shop/partials/shop_agent_feedback.html",
            {"show_error": True, "error": "Veuillez entrer au moins 2 caracteres."},
            status=400,
        )
    agent, error = verify_agent_and_create_shop_session(order, agent_name)
    if error:
        return render(
            request,
            "shop/partials/shop_agent_feedback.html",
            {"show_error": True, "error": error},
            status=400,
        )
    session = (
        ShopCashPaymentSession.objects.filter(
            order=order,
            agent=agent,
            is_used=False,
            expires_at__gt=timezone.now(),
        )
        .select_related("agent__user")
        .order_by("-created_at")
        .first()
    )
    response = render(
        request,
        "shop/partials/shop_agent_confirmed.html",
        {"agent": agent, "session": session},
    )
    response["HX-Trigger"] = '{"toast": {"type": "success", "message": "Agent verifie avec succes!"}}'
    return response


@login_required
@require_GET
def shop_payment_receipt(request, pk):
    payment = get_object_or_404(ShopPayment.objects.select_related("order"), pk=pk)
    user_is_manager = is_manager(request.user)
    manager_branch = get_user_branch(request.user) if user_is_manager else None
    can_view_as_manager = bool(manager_branch and manager_branch.pk == payment.order.branch_id)
    can_view_as_owner = payment.order.student_id == request.user.id
    if not (can_view_as_owner or can_view_as_manager or request.user.is_superuser):
        return HttpResponse("Non autorise", status=403)
    if not payment.receipt_pdf:
        raise Http404("Recu indisponible.")
    return FileResponse(payment.receipt_pdf.open("rb"), as_attachment=True, filename=f"recu-boutique-{payment.receipt_number}.pdf")


@manager_required
@require_POST
def manager_product_create(request):
    form = ShopProductForm(request.POST, request.FILES)
    if not form.is_valid():
        return render_manager_shop_panel(request, product_form=form, status=400)
    product = form.save(commit=False)
    product.branch = request.branch
    product.save()
    for image in request.FILES.getlist("gallery_images"):
        ShopProductImage.objects.create(product=product, image=image, is_cover=not product.gallery_images.exists())
    notify_shop_promotion_published(product=product, actor=request.user)
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request, product_form=ShopProductForm())
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_product_delete(request, pk):
    product = get_object_or_404(ShopProduct, pk=pk, branch=request.branch)
    # Catalogue items can be part of a sale or a stock movement. Archive or
    # restore them instead of deleting the accounting and stock history.
    product.is_active = not product.is_active
    product.save(update_fields=["is_active", "updated_at"])
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request)
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_stock_in(request):
    form = ShopStockInForm(request.POST, branch=request.branch)
    if not form.is_valid():
        return render_manager_shop_panel(request, stock_form=form, status=400)
    ShopStockMovement.objects.create(
        branch=request.branch,
        product=form.cleaned_data["product"],
        movement_type=ShopStockMovement.TYPE_IN,
        quantity=form.cleaned_data["quantity"],
        reference=next_shop_reference(request.branch, ShopSequence.TYPE_STOCK),
        notes=form.cleaned_data.get("notes", ""),
        created_by=request.user,
    )
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request, stock_form=ShopStockInForm(branch=request.branch))
    return manager_shop_redirect(request)


@manager_required
@require_GET
def manager_product_edit(request, pk):
    product = get_object_or_404(
        ShopProduct.objects.prefetch_related("gallery_images"),
        pk=pk,
        branch=request.branch,
    )
    return render_manager_shop_panel(
        request,
        product_form=ShopProductForm(instance=product),
        editing_product=product,
    )


@manager_required
@require_POST
def manager_product_update(request, pk):
    product = get_object_or_404(ShopProduct, pk=pk, branch=request.branch)
    promotion_was_published = product.is_active and product.sale_price is not None
    form = ShopProductForm(request.POST, request.FILES, instance=product)
    if not form.is_valid():
        return render_manager_shop_panel(
            request,
            product_form=form,
            editing_product=product,
            status=400,
        )
    product = form.save()
    for image in request.FILES.getlist("gallery_images"):
        ShopProductImage.objects.create(product=product, image=image, is_cover=not product.gallery_images.exists())
    if not promotion_was_published:
        notify_shop_promotion_published(product=product, actor=request.user)
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request, product_form=ShopProductForm())
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_product_image_cover(request, pk):
    image = get_object_or_404(
        ShopProductImage.objects.select_related("product"),
        pk=pk,
        product__branch=request.branch,
    )
    with transaction.atomic():
        ShopProductImage.objects.filter(product=image.product).update(is_cover=False)
        image.is_cover = True
        image.save(update_fields=["is_cover"])
        # Keep the longstanding primary-image field as the public cover.
        image.product.image = image.image.name
        image.product.save(update_fields=["image", "updated_at"])
    product = ShopProduct.objects.prefetch_related("gallery_images").get(pk=image.product_id)
    return render_manager_shop_panel(
        request,
        product_form=ShopProductForm(instance=product),
        editing_product=product,
    )


@manager_required
@require_POST
def manager_product_image_delete(request, pk):
    image = get_object_or_404(
        ShopProductImage.objects.select_related("product"),
        pk=pk,
        product__branch=request.branch,
    )
    product = image.product
    was_cover = image.is_cover
    image.delete()
    if was_cover:
        next_cover = product.gallery_images.order_by("id").first()
        if next_cover:
            next_cover.is_cover = True
            next_cover.save(update_fields=["is_cover"])
            product.image = next_cover.image.name
        else:
            product.image = None
        product.save(update_fields=["image", "updated_at"])
    product = ShopProduct.objects.prefetch_related("gallery_images").get(pk=product.pk)
    return render_manager_shop_panel(
        request,
        product_form=ShopProductForm(instance=product),
        editing_product=product,
    )


@manager_required
@require_POST
def manager_stock_adjust(request):
    form = ShopStockAdjustmentForm(request.POST, branch=request.branch)
    if not form.is_valid():
        return render_manager_shop_panel(request, stock_adjustment_form=form, status=400)

    try:
        with transaction.atomic():
            product = ShopProduct.objects.select_for_update().get(
                pk=form.cleaned_data["product"].pk,
                branch=request.branch,
                is_active=True,
            )
            quantity = form.cleaned_data["quantity"]
            if quantity < 0:
                ensure_stock_available(product=product, quantity=abs(quantity))
            ShopStockMovement.objects.create(
                branch=request.branch,
                product=product,
                movement_type=ShopStockMovement.TYPE_ADJUSTMENT,
                quantity=quantity,
                reference=next_shop_reference(request.branch, ShopSequence.TYPE_STOCK),
                notes=form.cleaned_data["notes"],
                created_by=request.user,
            )
    except ValidationError as exc:
        form.add_error(None, exc)
        return render_manager_shop_panel(request, stock_adjustment_form=form, status=400)
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request, stock_adjustment_form=ShopStockAdjustmentForm(branch=request.branch))
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_counter_order_create(request):
    form = ShopCounterOrderForm(request.POST, branch=request.branch)
    if not form.is_valid():
        return render_manager_shop_panel(request, counter_order_form=form, status=400)
    student = form.cleaned_data.get("student")
    try:
        create_counter_order(
            branch=request.branch,
            lines=form.cart_lines,
            payment_method=form.cleaned_data["payment_method"],
            created_by=request.user,
            student=student,
            customer_name=form.cleaned_data.get("customer_name", ""),
            customer_email=form.cleaned_data.get("customer_email", ""),
            customer_phone=form.cleaned_data.get("customer_phone", ""),
            immediate_settlement=True,
        )
    except ValidationError as exc:
        form.add_error(None, str(exc))
        return render_manager_shop_panel(request, counter_order_form=form, status=400)
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request, counter_order_form=ShopCounterOrderForm(branch=request.branch))
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_payment_validate(request, pk):
    payment = get_object_or_404(ShopPayment, pk=pk, order__branch=request.branch)
    try:
        validate_shop_payment(payment, user=request.user)
    except ValidationError as exc:
        return render_manager_shop_panel(request, shop_error=str(exc), status=400)
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request)
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_order_collect_cash(request, pk):
    """Record the actual cash collection for a remote student order."""
    try:
        with transaction.atomic():
            order = (
                ShopOrder.objects.select_for_update()
                .filter(
                    pk=pk,
                    branch=request.branch,
                    status=ShopOrder.STATUS_PENDING_PAYMENT,
                )
                .first()
            )
            if not order:
                raise ValidationError("Cette commande n'est plus a encaisser.")
            if order.payments.filter(status=ShopPayment.STATUS_PENDING).exists():
                raise ValidationError("Un paiement est deja en attente de validation.")
            amount = order.balance
            if amount <= 0:
                raise ValidationError("Le solde de cette commande est deja regle.")
            create_shop_payment(
                order,
                amount,
                ShopPayment.METHOD_CASH,
                request.user,
                auto_validate=True,
                agent=_payment_agent_for_branch_manager(request.user, request.branch),
            )
    except ValidationError as exc:
        return render_manager_shop_panel(request, shop_error=str(exc), status=400)
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request)
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_order_mark_ready(request, pk):
    order = get_object_or_404(ShopOrder, pk=pk, branch=request.branch)
    mark_order_ready(order, request.user)
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request)
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_order_deliver(request, pk):
    order = get_object_or_404(ShopOrder, pk=pk, branch=request.branch)
    deliver_order(order, request.user)
    if request.headers.get("HX-Request"):
        return render_manager_shop_panel(request)
    return manager_shop_redirect(request)


@manager_required
@require_POST
def manager_shop_cash_session_regenerate(request, pk):
    manager_agent = _payment_agent_for_branch_manager(request.user, request.branch)
    if not manager_agent:
        return HttpResponse("Aucun profil agent pour cette annexe.", status=403)
    session = get_object_or_404(
        ShopCashPaymentSession.objects.select_related("order", "agent__user"),
        pk=pk,
        agent=manager_agent,
        is_used=False,
    )
    session.generate_code()
    return render(
        request,
        "shop/partials/manager_shop_cash_session_card.html",
        {
            "session": session,
            "manager_agent": manager_agent,
            "show_regenerated_notice": True,
        },
    )


@manager_required
@require_POST
def manager_shop_cash_session_cancel(request, pk):
    manager_agent = _payment_agent_for_branch_manager(request.user, request.branch)
    if not manager_agent:
        return HttpResponse("Aucun profil agent pour cette annexe.", status=403)
    session = get_object_or_404(
        ShopCashPaymentSession,
        pk=pk,
        agent=manager_agent,
        is_used=False,
    )
    session.is_used = True
    session.save(update_fields=["is_used"])
    return HttpResponse(
        "<p class=\"rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-center text-sm text-slate-600\">Session boutique annulee.</p>",
    )
