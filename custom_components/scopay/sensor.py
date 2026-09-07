"""SCOPAY sensors: balances, alerts, last transaction and spend analysis."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CURRENCY_GBP, DOMAIN
from .coordinator import ScopayConfigEntry, ScopayCoordinator
from .parse import ScopayData


@dataclass(frozen=True, kw_only=True)
class ScopaySensorDescription(SensorEntityDescription):
    """A sensor description plus how to pull its value/attributes from the data."""

    value_fn: Callable[[ScopayData], float | int | str | None]
    attributes_fn: Callable[[ScopayData], dict[str, Any]] | None = None


def _last_transaction_attrs(data: ScopayData) -> dict[str, Any]:
    txn = data.last_transaction
    return {"date": txn.date, "description": txn.description} if txn else {}


def _catering_attrs(data: ScopayData) -> dict[str, Any]:
    return {
        "display": data.catering_display,
        "products": [
            {
                "name": product.name,
                "product_id": product.product_id,
                "balance": product.balance,
                "owed": product.owed,
            }
            for product in data.products
        ],
    }


# Typical school days in a month (~190 days over ~10 school months). Used only to
# turn a per-school-day average into a monthly figure for budgeting.
SCHOOL_DAYS_PER_MONTH = 19


def _spend_rows(data: ScopayData, days: int) -> list:
    """Spend (negative) transactions in the last `days` days, newest first.

    Positive rows are money IN - top-ups and item payments - so they are not
    spend and are excluded here.
    """
    cutoff = dt_util.now().date() - timedelta(days=days)
    return [
        txn
        for txn in data.transactions
        if txn.amount is not None and txn.amount < 0 and txn.on and txn.on >= cutoff
    ]


def _spend_total(data: ScopayData, days: int) -> float | None:
    rows = _spend_rows(data, days)
    return round(sum(-txn.amount for txn in rows), 2) if rows else 0.0


def _avg_per_school_day(data: ScopayData) -> float | None:
    """Mean spend on days she actually spent, over the last 30 days.

    Averaging over *spend days* rather than calendar days keeps holidays and
    weekends from dragging the figure down.
    """
    rows = _spend_rows(data, 30)
    if not rows:
        return None
    return round(sum(-txn.amount for txn in rows) / len({txn.on for txn in rows}), 2)


def _projected_monthly(data: ScopayData) -> float | None:
    avg = _avg_per_school_day(data)
    return round(avg * SCHOOL_DAYS_PER_MONTH, 2) if avg is not None else None


def _spend_attrs(data: ScopayData) -> dict[str, Any]:
    rows = _spend_rows(data, 30)
    return {
        "spend_days": len({txn.on for txn in rows}),
        "transactions": len(rows),
        "recent": [
            {
                "date": txn.date,
                "amount": txn.amount,
                "description": txn.description,
            }
            for txn in rows[:10]
        ],
    }


SENSORS: tuple[ScopaySensorDescription, ...] = (
    ScopaySensorDescription(
        key="catering_balance",
        translation_key="catering_balance",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_GBP,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:silverware-fork-knife",
        value_fn=lambda data: data.catering_balance,
        attributes_fn=_catering_attrs,
    ),
    ScopaySensorDescription(
        key="amount_owed",
        translation_key="amount_owed",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_GBP,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:cash-remove",
        value_fn=lambda data: data.owed_total,
    ),
    ScopaySensorDescription(
        key="last_transaction",
        translation_key="last_transaction",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_GBP,
        suggested_display_precision=2,
        icon="mdi:receipt-text",
        value_fn=lambda data: (
            data.last_transaction.amount if data.last_transaction else None
        ),
        attributes_fn=_last_transaction_attrs,
    ),
    ScopaySensorDescription(
        key="alerts",
        translation_key="alerts",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:bell-alert",
        value_fn=lambda data: data.alerts,
    ),
    ScopaySensorDescription(
        key="catering_spend_7d",
        translation_key="catering_spend_7d",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_GBP,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:calendar-week",
        value_fn=lambda data: _spend_total(data, 7),
    ),
    ScopaySensorDescription(
        key="catering_spend_30d",
        translation_key="catering_spend_30d",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_GBP,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        icon="mdi:calendar-month",
        value_fn=lambda data: _spend_total(data, 30),
        attributes_fn=_spend_attrs,
    ),
    ScopaySensorDescription(
        key="catering_avg_per_school_day",
        translation_key="catering_avg_per_school_day",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_GBP,
        suggested_display_precision=2,
        icon="mdi:chart-line",
        value_fn=_avg_per_school_day,
    ),
    ScopaySensorDescription(
        key="catering_projected_monthly",
        translation_key="catering_projected_monthly",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_GBP,
        suggested_display_precision=2,
        icon="mdi:cash-clock",
        value_fn=_projected_monthly,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScopayConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SCOPAY sensors for a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        ScopaySensor(coordinator, entry, description) for description in SENSORS
    )


class ScopaySensor(CoordinatorEntity[ScopayCoordinator], SensorEntity):
    """A single SCOPAY value for one pupil."""

    entity_description: ScopaySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ScopayCoordinator,
        entry: ScopayConfigEntry,
        description: ScopaySensorDescription,
    ) -> None:
        """Bind the sensor to its coordinator and pupil device."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"SCOPAY {coordinator.data.pupil}"
            if coordinator.data.pupil
            else "SCOPAY",
            manufacturer="Tucasi",
            model="SCOPAY",
        )

    @property
    def native_value(self) -> float | int | str | None:
        """Return the current value for this sensor."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes, if this sensor exposes any."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)
