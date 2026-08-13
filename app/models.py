from sqlalchemy import Column, Integer, String, Date, ForeignKey, Boolean, Table, DateTime, BigInteger, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base
from sqlalchemy.dialects.postgresql import JSONB

products_products_consola = Table(
    "products_products_consola", Base.metadata,
    Column("products_id", Integer, ForeignKey("products_products.id_product"), primary_key=True),
    Column("consoles_id", Integer, ForeignKey("products_consoles.id_console"), primary_key=True),
)

class Product(Base):
    __tablename__ = "products_products"
    id_product = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(100), default="")
    description = Column(String, default="")
    date_register = Column(Date, default=datetime.now)
    date_last_modified = Column(Date, default=datetime.now)
    image = Column(String(500), default="")
    calification = Column(Integer, default=0)
    puntos_venta = Column(Integer, default=0)
    puede_rentarse = Column(Boolean, default=True)
    destacado = Column(Boolean, default=False)
    oferta_semana = Column(Boolean, default=False)
    type_id_id = Column(String(50), default="")
    tipo_juego_id = Column(String(50), default="")
    consoles = relationship("Consoles", secondary=products_products_consola, back_populates="products", lazy="selectin")


class GameDetail(Base):
    __tablename__ = "products_gamedetail"

    id_game_detail = Column(Integer, primary_key=True, autoincrement=True)
    producto_id = Column(Integer, ForeignKey("products_products.id_product"), nullable=True)
    consola_id = Column(Integer, ForeignKey("products_consoles.id_console"), nullable=True)       # ajustar tabla/columna
    licencia_id = Column(Integer, ForeignKey("products_licenses.id_license"), nullable=True)      # ajustar tabla/columna
    cuenta_id = Column(Integer, ForeignKey("products_productaccounts.id_product_accounts"), nullable=True)         # ajustar tabla/columna

    duracion_dias_alquiler = Column(Integer, nullable=True)
    stock = Column(Integer, default=0)
    precio = Column(Integer, default=0)
    precio_descuento = Column(Integer, default=0)

    # relaciones — ajusta los nombres de las clases si difieren en tu proyecto
    producto = relationship("Product", backref="game_details")
    consola = relationship("Consoles", backref="game_details")
    licencia = relationship("Licenses", backref="game_details")
    cuenta = relationship("ProductAccounts", backref="game_details")

    def __str__(self) -> str:
        return f"{self.consola} {self.licencia}"


class TypeAccounts(Base):
    __tablename__ = "products_typeaccounts"

    id_type_accounts = Column(Integer, primary_key=True, autoincrement=True)
    descripcion = Column(String(100), default="")

    def __str__(self) -> str:
        return getattr(self, "descripcion", "")


class Consoles(Base):
    __tablename__ = "products_consoles"

    id_console = Column(Integer, primary_key=True, autoincrement=True)
    descripcion = Column(String(100))
    estado = Column(Boolean, nullable=True)

    # relación inversa many-to-many — debe coincidir con Product.consoles
    products = relationship(
        "Product",
        secondary=products_products_consola,
        back_populates="consoles",
        lazy="selectin",
    )

    def __str__(self) -> str:
        return self.descripcion

    def get_id_console(self) -> int:
        return self.id_console


class Licenses(Base):
    __tablename__ = "products_licenses"

    id_license = Column(Integer, primary_key=True, autoincrement=True)
    descripcion = Column(String(100))

    def __str__(self) -> str:
        return self.descripcion

    def get_id_licence(self) -> int:
        return self.id_license


class ProductAccounts(Base):
    __tablename__ = "products_productaccounts"

    id_product_accounts = Column(Integer, primary_key=True, autoincrement=True)
    cuenta = Column(String(200))
    password = Column(String(100), nullable=True)
    activa = Column(Boolean, default=False)
    tipo_cuenta_id = Column(Integer, ForeignKey("products_typeaccounts.id_type_accounts"), nullable=True, default=1)
    dias_duracion = Column(Integer, default=0, nullable=True)
    codigo_seguridad = Column(String(500), nullable=True)

    tipo_cuenta = relationship("TypeAccounts", backref="product_accounts")

    def __str__(self) -> str:
        return self.cuenta
    
class User(Base):
    __tablename__ = "auth_user"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    password = Column(String(128), nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)
    is_superuser = Column(Boolean, nullable=False, default=False)
    username = Column(String(150), unique=True, index=True, nullable=False)
    first_name = Column(String(150), nullable=False, default="")
    last_name = Column(String(150), nullable=False, default="")
    email = Column(String(254), nullable=False, default="")
    is_staff = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    date_joined = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class UserCustomized(Base):
    __tablename__ = "users_user_customized"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("auth_user.id"), unique=True, nullable=False)
    phone_number = Column(String(50), nullable=False, default="")
    avatar = Column(String(500), nullable=False, default="")
    puntos = Column(Integer, nullable=False, default=0)
    balance_exchange = Column(Integer, nullable=False, default=0)

    user = relationship("User", backref="custom_profile", lazy="joined")


class LikedGame(Base):
    __tablename__ = "user_liked_games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("auth_user.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products_products.id_product"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    user = relationship("User", backref="liked_games")
    product = relationship("Product", backref="liked_by_users")


class OrderBuy(Base):
    __tablename__ = "orders_buy"

    id_order = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("auth_user.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products_products.id_product"), nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    file_path = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    modified_at = Column(DateTime(timezone=True), nullable=True, default=None, onupdate=datetime.utcnow)
    description_order = Column(String(500), nullable=False, default="")

    id_license = Column(Integer, ForeignKey("products_licenses.id_license"), nullable=True)
    id_console = Column(Integer, ForeignKey("products_consoles.id_console"), nullable=True)

    # Snapshot del precio pagado al momento de la orden. Nullable porque las
    # ordenes creadas antes de este campo no lo tienen -- no se puede
    # reconstruir retroactivamente, y no hace falta: sorteos solo cuenta
    # ordenes dentro del rango de fechas del sorteo (siempre posterior).
    amount = Column(Integer, nullable=True)

    user = relationship("User", backref="orders_buy")
    product = relationship("Product", backref="orders")


class SaleDetail(Base):
    __tablename__ = "products_saledetail"

    id_sale_detail = Column(Integer, primary_key=True, autoincrement=True)
    fecha_venta = Column(DateTime(timezone=True), nullable=False)
    fecha_vencimiento = Column(Date, nullable=True)
    cuenta_id = Column(Integer, ForeignKey("products_productaccounts.id_product_accounts"), nullable=True)
    producto_id = Column(Integer, ForeignKey("products_products.id_product"), nullable=True)
    usuario_id = Column(Integer, ForeignKey("auth_user.id"), nullable=True)
    combinacion_id = Column(Integer, ForeignKey("products_gamedetail.id_game_detail"), nullable=True)

    cuenta = relationship("ProductAccounts", backref="sale_details")
    producto = relationship("Product", backref="sale_details")
    usuario = relationship("User", backref="sale_details")
    combinacion = relationship("GameDetail", backref="sale_details")


class ShoppingCar(Base):
    __tablename__ = "products_shoppingcar"

    id_shopping_car = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column("usuario_id", Integer, ForeignKey("auth_user.id"), nullable=False)
    product_id = Column("producto_id", Integer, ForeignKey("products_gamedetail.id_game_detail"), nullable=False)
    estado = Column(Boolean, nullable=False, default=True)

    user = relationship("User", backref="shopping_cars")
    product = relationship("GameDetail", backref="shopping_cars")


class Coupon(Base):
    __tablename__ = "coupons_coupon"

    id_coupon = Column(Integer, primary_key=True, autoincrement=True)
    name_coupon = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    modified_at = Column(DateTime(timezone=True), nullable=True, default=None, onupdate=datetime.utcnow)
    expiration_date = Column(DateTime(timezone=True), nullable=False)
    is_valid = Column(Boolean, nullable=False, default=True)
    user_id = Column(Integer, ForeignKey("auth_user.id"), nullable=True)
    percentage_off = Column(Integer, nullable=False, default=0)
    points_given = Column(Integer, nullable=False, default=0)
    discount_type = Column(String(20), nullable=False, default="PERCENTAGE")
    fixed_amount = Column(Integer, nullable=False, default=0)
    source = Column(String(30), nullable=False, default="MANUAL")

    user = relationship("User", backref="coupons")
    # game_details M2M is accessed via CouponGameDetail junction below


class CouponGameDetail(Base):
    """Junction table for Coupon.game_details ManyToManyField (Django-managed).

    Django generates this as ``coupons_coupon_game_details``.
    Columns: id, coupon_id, gamedetail_id.
    """

    __tablename__ = "coupons_coupon_game_details"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    coupon_id = Column(Integer, ForeignKey("coupons_coupon.id_coupon"), nullable=False)
    gamedetail_id = Column(Integer, ForeignKey("products_gamedetail.id_game_detail"), nullable=False)


class CouponRule(Base):
    """Business rule attached to a coupon (Django-managed table).

    This mirrors the ``products_couponrule`` model in the Django ``products`` app
    and is used only for reads from the FastAPI side.
    """

    __tablename__ = "products_couponrule"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    coupon_id = Column(Integer, ForeignKey("coupons_coupon.id_coupon"), nullable=False)
    rule_type = Column(String(50), nullable=False)
    operator = Column(String(10), nullable=False)
    value = Column(JSONB, nullable=False)

    coupon = relationship("Coupon", backref="rules")


class CouponRedemption(Base):
    """Redemption log for coupons (Django-managed table).

    Records each time a coupon is actually redeemed in an order. This table is
    *not* written from FastAPI in this endpoint; it is only queried to enforce
    usage limits.
    """

    __tablename__ = "products_couponredemption"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    coupon_id = Column(Integer, ForeignKey("coupons_coupon.id_coupon"), nullable=False)
    user_id = Column(Integer, ForeignKey("auth_user.id"), nullable=False)
    order_id = Column(String(100), nullable=False)
    redeemed_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    coupon = relationship("Coupon", backref="redemptions")
    user = relationship("User", backref="coupon_redemptions")


class ProductAlias(Base):
    __tablename__ = "products_productalias"
    id = Column(Integer, primary_key=True, autoincrement=True)
    alias = Column(String(200), nullable=False)
    producto_id = Column(Integer, ForeignKey("products_products.id_product"), nullable=False)
    created_at = Column(DateTime, default=datetime.now)


# ============================================================================
# HARDCORE REWARDS
# ============================================================================

class PointTransaction(Base):
    """Ledger de movimientos de puntos. Toda alta o baja de UserCustomized.puntos
    debe quedar registrada aqui (compra, giro de ruleta, canje, ajuste manual,
    devolucion), para poder auditar el saldo en cualquier momento.
    """

    __tablename__ = "rewards_pointtransaction"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('PURCHASE','ROULETTE_SPIN','COUPON','EXCHANGE','ADMIN_ADJUST','REFUND')",
            name="rewards_pointtransaction_reason_check",
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("auth_user.id"), nullable=False)
    delta = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    reason = Column(String(30), nullable=False)
    reference_type = Column(String(50), nullable=True)
    reference_id = Column(String(100), nullable=True)
    description = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    user = relationship("User", backref="point_transactions")


class Roulette(Base):
    """Una rueda configurable. Puede haber varias en el tiempo (ej. edicion
    de temporada) pero solo una activa a la vez en la practica.
    """

    __tablename__ = "rewards_roulette"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    cost_points = Column(Integer, nullable=False, default=0)
    max_spins_per_day = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class RoulettePrize(Base):
    """Premio configurable de una rueda. El backend nunca expone `weight`
    (probabilidad relativa) al cliente.
    """

    __tablename__ = "rewards_rouletteprize"
    __table_args__ = (
        CheckConstraint(
            "prize_type IN ('COUPON_FIXED','COUPON_PERCENT','POINTS','NOTHING','MANUAL_CLAIM')",
            name="rewards_rouletteprize_type_check",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    roulette_id = Column(Integer, ForeignKey("rewards_roulette.id"), nullable=False)
    name = Column(String(100), nullable=False)
    prize_type = Column(String(20), nullable=False)
    value = Column(Integer, nullable=False, default=0)
    weight = Column(Integer, nullable=False, default=1)
    coupon_validity_minutes = Column(Integer, nullable=True)
    min_purchase = Column(Integer, nullable=True)
    max_per_user = Column(Integer, nullable=True)
    stock = Column(Integer, nullable=True)
    color = Column(String(20), nullable=False, default="#7c3aed")
    display_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    roulette = relationship("Roulette", backref="prizes")


class RouletteSpin(Base):
    """Auditoria de cada giro: quien, cuando, que le toco y que cupon generó."""

    __tablename__ = "rewards_roulettespin"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="rewards_roulettespin_idempotency_key_key"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("auth_user.id"), nullable=False)
    roulette_id = Column(Integer, ForeignKey("rewards_roulette.id"), nullable=False)
    prize_id = Column(Integer, ForeignKey("rewards_rouletteprize.id"), nullable=False)
    points_spent = Column(Integer, nullable=False, default=0)
    coupon_id = Column(Integer, ForeignKey("coupons_coupon.id_coupon"), nullable=True)
    idempotency_key = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    user = relationship("User", backref="roulette_spins")
    roulette = relationship("Roulette", backref="spins")
    prize = relationship("RoulettePrize", backref="spins")
    coupon = relationship("Coupon", backref="roulette_spin")


# ============================================================================
# SORTEOS
# ============================================================================

class Sorteo(Base):
    """Un sorteo configurable por el admin. La calificacion de participantes
    NO se materializa en una tabla propia: se calcula en vivo contra
    OrderBuy (status='completed', created_at dentro del rango del sorteo),
    para que un reembolso posterior saque al cliente de la lista sin
    necesidad de un job de sincronizacion.
    """

    __tablename__ = "sorteos_sorteo"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','ACTIVE','FINISHED')",
            name="sorteos_sorteo_status_check",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(150), nullable=False)
    legend = Column(String(1000), nullable=False, default="")
    prize_image_url = Column(String(500), nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    min_purchases = Column(Integer, nullable=True)
    min_amount = Column(Integer, nullable=True)
    require_both = Column(Boolean, nullable=False, default=False)
    winners_count = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="DRAFT")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class SorteoWinner(Base):
    """Ganador de un sorteo ya ejecutado. drawn_at queda fijo en el momento
    del sorteo aleatorio; el nombre/correo del usuario se resuelven en vivo
    via join a auth_user, no se copian aqui.
    """

    __tablename__ = "sorteos_winner"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sorteo_id = Column(Integer, ForeignKey("sorteos_sorteo.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("auth_user.id"), nullable=False)
    drawn_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    sorteo = relationship("Sorteo", backref="winners")
    user = relationship("User", backref="sorteo_wins")
