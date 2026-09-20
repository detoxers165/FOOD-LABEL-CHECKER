from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Money(FlexibleModel):
    value: float | None = None
    currency: str | None = None


class Quantity(FlexibleModel):
    value: float | None = None
    unit: str | None = None


class ProductSchema(FlexibleModel):
    brand: str | None = None
    product_name: str | None = None
    category: str | None = None
    variant: str | None = None
    net_quantity: Quantity | None = None
    unit: str | None = None
    mrp: Money | None = None
    unit_sale_price: Money | None = None
    batch_number: str | None = None
    manufacturing_date: str | None = None
    expiry_date: str | None = None
    best_before: str | None = None
    fssai_license_number: str | None = None
    manufacturer: str | None = None
    packer: str | None = None
    marketer: str | None = None
    country_of_origin: str | None = None
    additional_fields: dict[str, Any] = Field(default_factory=dict)


class AllergensSchema(FlexibleModel):
    contains: list[str] = Field(default_factory=list)
    may_contain: list[str] = Field(default_factory=list)


class NutritionSchema(FlexibleModel):
    energy: Quantity | None = None
    protein: Quantity | None = None
    carbohydrate: Quantity | None = None
    total_sugars: Quantity | None = None
    added_sugars: Quantity | None = None
    dietary_fibre: Quantity | None = None
    total_fat: Quantity | None = None
    saturated_fat: Quantity | None = None
    trans_fat: Quantity | None = None
    sodium: Quantity | None = None
    salt: Quantity | None = None
    cholesterol: Quantity | None = None
    other_nutrients: dict[str, Quantity | Any] = Field(
        default_factory=dict
    )


class ContactInformationSchema(FlexibleModel):
    consumer_care: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    address: str | None = None
