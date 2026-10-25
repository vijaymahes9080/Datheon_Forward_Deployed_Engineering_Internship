"""Controlled ERP/CRM Business Tool Registry and Sandboxed Mock Implementations."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class OperationType(str, Enum):
    INVENTORY_LOOKUP = "inventory_lookup"
    CUSTOMER_LOOKUP = "customer_lookup"
    LEAD_STATUS_UPDATE = "lead_status_update"
    SUPPORT_TICKET_CREATE = "support_ticket_create"
    TICKET_STATUS_LOOKUP = "ticket_status_lookup"
    TRANSACTION_STATUS_VERIFY = "transaction_status_verify"


# =====================================================================
# Strict Pydantic Schemas for Tools
# =====================================================================

class InventoryLookupInput(BaseModel):
    sku: str = Field(description="Stock Keeping Unit identifier", min_length=3, max_length=32)
    location_id: Optional[str] = Field(default=None, description="Optional warehouse zone or location")


class CustomerLookupInput(BaseModel):
    customer_id: str = Field(description="Unique customer identifier", min_length=3, max_length=32)


class LeadStatusUpdateInput(BaseModel):
    lead_id: str = Field(description="Lead record identifier", min_length=3, max_length=32)
    new_status: str = Field(description="Updated status: QUALIFIED, CONTACTED, CLOSED_WON, CLOSED_LOST")
    note: str = Field(description="Audit justification note", min_length=5, max_length=500)


class SupportTicketCreateInput(BaseModel):
    customer_id: str = Field(description="Target customer identifier", min_length=3, max_length=32)
    priority: str = Field(default="normal", description="Priority level: low, normal, high, urgent")
    title: str = Field(description="Short incident or request title", min_length=3, max_length=120)
    description: str = Field(description="Detailed issue description", min_length=10, max_length=2000)


class TicketStatusLookupInput(BaseModel):
    ticket_id: str = Field(description="Support ticket identifier", min_length=3, max_length=32)


class TransactionStatusVerifyInput(BaseModel):
    transaction_id: str = Field(description="Transaction ID to reconcile", min_length=3, max_length=64)


# =====================================================================
# Sandboxed Business Service Implementation
# =====================================================================

class SandboxedERPService:
    """Mock in-memory transactional ERP/CRM service with realistic enterprise records."""

    def __init__(self):
        # Pre-seed inventory catalog
        self.inventory_db: Dict[str, Dict[str, Any]] = {
            "SKU-INV-1001": {
                "sku": "SKU-INV-1001",
                "name": "Edge Gateway Appliance Gen4",
                "stock": 142,
                "reorder_threshold": 25,
                "location": "Zone-A-Rack-12",
                "price": 1299.00,
            },
            "SKU-INV-1002": {
                "sku": "SKU-INV-1002",
                "name": "Optical Transceiver 100G QSFP28",
                "stock": 420,
                "reorder_threshold": 50,
                "location": "Zone-B-Rack-04",
                "price": 185.50,
            },
            "SKU-INV-1005": {
                "sku": "SKU-INV-1005",
                "name": "Secure Enclave Hardware Module",
                "stock": 88,
                "reorder_threshold": 20,
                "location": "Vault-Alpha-01",
                "price": 899.00,
            },
        }

        # Pre-seed customer accounts
        self.customers_db: Dict[str, Dict[str, Any]] = {
            "CUST-001": {
                "customer_id": "CUST-001",
                "name": "Acme Global Dynamics",
                "tier": "Enterprise Platinum",
                "contact_email": "ops@acmeglobal.com",
                "account_manager": "Sarah Jenkins",
                "status": "ACTIVE",
            },
            "CUST-002": {
                "customer_id": "CUST-002",
                "name": "Vertex Logistics Network",
                "tier": "Enterprise Gold",
                "contact_email": "procurement@vertex.org",
                "account_manager": "David Chen",
                "status": "ACTIVE",
            },
        }

        # Pre-seed CRM leads
        self.leads_db: Dict[str, Dict[str, Any]] = {
            "LEAD-501": {
                "lead_id": "LEAD-501",
                "company": "Nexus Financial Systems",
                "contact_name": "Elena Rostova",
                "estimated_arr": 150000.0,
                "status": "QUALIFIED",
                "last_note": "Initial architectural discovery completed.",
            },
            "LEAD-502": {
                "lead_id": "LEAD-502",
                "company": "Helios BioTech Group",
                "contact_name": "Marcus Aurelius",
                "estimated_arr": 85000.0,
                "status": "CONTACTED",
                "last_note": "Awaiting security compliance sign-off.",
            },
        }

        # Support tickets
        self.tickets_db: Dict[str, Dict[str, Any]] = {
            "TICK-901": {
                "ticket_id": "TICK-901",
                "customer_id": "CUST-001",
                "priority": "high",
                "title": "VPN Gateway throughput degradation",
                "status": "IN_PROGRESS",
                "created_at": "2026-10-20T14:30:00Z",
            }
        }

    # --- Tool Call Implementations ---

    def inventory_lookup(self, params: InventoryLookupInput) -> Dict[str, Any]:
        sku_clean = params.sku.strip().upper()
        if sku_clean in self.inventory_db:
            return {"found": True, "item": self.inventory_db[sku_clean]}
        return {"found": False, "message": f"SKU {params.sku} not found in inventory."}

    def customer_lookup(self, params: CustomerLookupInput) -> Dict[str, Any]:
        cust_id = params.customer_id.strip().upper()
        if cust_id in self.customers_db:
            return {"found": True, "customer": self.customers_db[cust_id]}
        return {"found": False, "message": f"Customer {params.customer_id} not found."}

    def lead_status_update(self, params: LeadStatusUpdateInput) -> Dict[str, Any]:
        lead_id = params.lead_id.strip().upper()
        if lead_id not in self.leads_db:
            return {"success": False, "message": f"Lead {params.lead_id} does not exist."}
        lead = self.leads_db[lead_id]
        old_status = lead["status"]
        lead["status"] = params.new_status.upper()
        lead["last_note"] = params.note
        lead["updated_at"] = datetime.now(timezone.utc).isoformat()
        return {
            "success": True,
            "lead_id": lead_id,
            "previous_status": old_status,
            "new_status": lead["status"],
            "note": params.note,
        }

    def support_ticket_create(self, params: SupportTicketCreateInput) -> Dict[str, Any]:
        ticket_id = f"TICK-{uuid.uuid4().hex[:6].upper()}"
        ticket = {
            "ticket_id": ticket_id,
            "customer_id": params.customer_id,
            "priority": params.priority.lower(),
            "title": params.title,
            "description": params.description,
            "status": "OPEN",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.tickets_db[ticket_id] = ticket
        return {"success": True, "ticket": ticket}

    def ticket_status_lookup(self, params: TicketStatusLookupInput) -> Dict[str, Any]:
        tid = params.ticket_id.strip().upper()
        if tid in self.tickets_db:
            return {"found": True, "ticket": self.tickets_db[tid]}
        return {"found": False, "message": f"Ticket {params.ticket_id} not found."}


# Singleton mock ERP service instance
_erp_service = None


def get_erp_service() -> SandboxedERPService:
    global _erp_service
    if _erp_service is None:
        _erp_service = SandboxedERPService()
    return _erp_service
