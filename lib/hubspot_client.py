"""HubSpot API Client

Handles all interactions with HubSpot CRM:
- Fetching Signals, Companies, and Contacts
- Creating associations between objects
- Pagination for bulk operations
"""

import os
from typing import Optional, Iterator
from hubspot import HubSpot


class HubSpotClient:
    """Client for HubSpot CRM operations."""
    
    # Custom object type IDs
    SIGNAL_OBJECT_TYPE = "2-54609655"
    COMPANY_OBJECT_TYPE = "0-2"
    CONTACT_OBJECT_TYPE = "0-1"
    
    # Association type IDs (Signal <-> Company/Contact)
    SIGNAL_TO_COMPANY_ASSOCIATION = 421
    SIGNAL_TO_CONTACT_ASSOCIATION = None  # Will be discovered
    
    def __init__(self, access_token: Optional[str] = None):
        """Initialize HubSpot client."""
        self.access_token = access_token or os.environ.get("HUBSPOT_ACCESS_TOKEN")
        if not self.access_token:
            raise ValueError("HubSpot access token required")
        
        self.client = HubSpot(access_token=self.access_token)
        
        # Discover association type for Signal -> Contact
        self._discover_association_types()
    
    def _discover_association_types(self):
        """Discover association type IDs between Signals and other objects."""
        try:
            response = self.client.crm.associations.v4.schema.definitions_api.get_all(
                from_object_type=self.SIGNAL_OBJECT_TYPE,
                to_object_type=self.CONTACT_OBJECT_TYPE
            )
            if response.results:
                self.SIGNAL_TO_CONTACT_ASSOCIATION = response.results[0].type_id
        except Exception as e:
            print(f"Warning: Could not discover association types: {e}", flush=True)
    
    # ==========================================
    # SIGNAL OPERATIONS
    # ==========================================
    
    def get_signal(self, signal_id: str) -> dict:
        """Fetch a Signal by ID with all relevant properties."""
        properties = [
            "signal_name",
            "signal_description", 
            "signal_citation",
            "signal_type",
            "signal_status",
            "signal_origin",
            "signal_weighting",
        ]
        
        response = self.client.crm.objects.basic_api.get_by_id(
            object_type=self.SIGNAL_OBJECT_TYPE,
            object_id=signal_id,
            properties=properties,
            associations=[self.COMPANY_OBJECT_TYPE, self.CONTACT_OBJECT_TYPE]
        )
        
        return {
            "id": response.id,
            "properties": response.properties,
            "associations": self._parse_associations(response.associations)
        }
    
    def _parse_associations(self, associations) -> dict:
        """Parse associations from HubSpot response."""
        result = {"companies": [], "contacts": []}
        
        if not associations:
            return result
            
        for obj_type, assoc_list in associations.items():
            if "company" in obj_type.lower():
                result["companies"] = [a.to_object_id for a in assoc_list.results]
            elif "contact" in obj_type.lower():
                result["contacts"] = [a.to_object_id for a in assoc_list.results]
        
        return result
    
    def list_signals(self, limit: int = 100, after: Optional[str] = None) -> dict:
        """List signals with pagination."""
        properties = [
            "signal_name",
            "signal_description",
            "signal_citation",
            "signal_type",
            "signal_status",
        ]
        
        response = self.client.crm.objects.basic_api.get_page(
            object_type=self.SIGNAL_OBJECT_TYPE,
            limit=limit,
            after=after,
            properties=properties,
            associations=[self.COMPANY_OBJECT_TYPE, self.CONTACT_OBJECT_TYPE]
        )
        
        results = []
        for signal in response.results:
            associations = self._parse_associations(signal.associations)
            results.append({
                "id": signal.id,
                "properties": signal.properties,
                "associations": associations
            })
        
        return {
            "results": results,
            "paging": {
                "next": response.paging.next.after if response.paging and response.paging.next else None
            }
        }
    
    def list_signals_without_associations(self, limit: int = 100) -> list:
        """List signals that don't have company or contact associations."""
        unassociated = []
        after = None
        
        while len(unassociated) < limit:
            page = self.list_signals(limit=min(100, limit - len(unassociated)), after=after)
            
            for signal in page["results"]:
                associations = signal.get("associations", {})
                companies = associations.get("companies", [])
                contacts = associations.get("contacts", [])
                
                # Include if no associations
                if not companies and not contacts:
                    unassociated.append(signal)
                    
                    if len(unassociated) >= limit:
                        break
            
            after = page["paging"]["next"]
            if not after:
                break
        
        return unassociated
    
    # ==========================================
    # COMPANY OPERATIONS  
    # ==========================================
    
    def get_company(self, company_id: str) -> dict:
        """Fetch a Company by ID."""
        response = self.client.crm.companies.basic_api.get_by_id(
            company_id=company_id,
            properties=["name", "domain"]
        )
        return {
            "id": response.id,
            "name": response.properties.get("name", ""),
            "domain": response.properties.get("domain", ""),
        }
    
    def list_companies(
        self, 
        limit: int = 100,
        after: Optional[str] = None,
        modified_after: Optional[str] = None
    ) -> dict:
        """List companies with pagination."""
        properties = ["name", "domain", "hs_lastmodifieddate"]
        
        if modified_after:
            filter_groups = [{
                "filters": [{
                    "propertyName": "hs_lastmodifieddate",
                    "operator": "GTE",
                    "value": modified_after
                }]
            }]
            response = self.client.crm.companies.search_api.do_search(
                public_object_search_request={
                    "filterGroups": filter_groups,
                    "properties": properties,
                    "limit": limit,
                    "after": after or "0"
                }
            )
        else:
            response = self.client.crm.companies.basic_api.get_page(
                limit=limit,
                after=after,
                properties=properties
            )
        
        results = []
        for company in response.results:
            results.append({
                "id": company.id,
                "name": company.properties.get("name", ""),
                "domain": company.properties.get("domain", ""),
            })
        
        return {
            "results": results,
            "paging": {
                "next": response.paging.next.after if response.paging and response.paging.next else None
            }
        }
    
    def iter_all_companies(self, modified_after: Optional[str] = None) -> Iterator[dict]:
        """Iterate through all companies with automatic pagination."""
        after = None
        while True:
            page = self.list_companies(limit=100, after=after, modified_after=modified_after)
            
            for company in page["results"]:
                yield company
            
            after = page["paging"]["next"]
            if not after:
                break
    
    # ==========================================
    # CONTACT OPERATIONS
    # ==========================================
    
    def get_contact(self, contact_id: str) -> dict:
        """Fetch a Contact by ID."""
        response = self.client.crm.contacts.basic_api.get_by_id(
            contact_id=contact_id,
            properties=["firstname", "lastname", "company"]
        )
        return {
            "id": response.id,
            "firstname": response.properties.get("firstname", ""),
            "lastname": response.properties.get("lastname", ""),
            "company": response.properties.get("company", ""),
        }
    
    def list_contacts(
        self,
        limit: int = 100,
        after: Optional[str] = None,
        modified_after: Optional[str] = None
    ) -> dict:
        """List contacts with pagination."""
        properties = ["firstname", "lastname", "company", "hs_lastmodifieddate"]
        
        if modified_after:
            filter_groups = [{
                "filters": [{
                    "propertyName": "hs_lastmodifieddate",
                    "operator": "GTE",
                    "value": modified_after
                }]
            }]
            response = self.client.crm.contacts.search_api.do_search(
                public_object_search_request={
                    "filterGroups": filter_groups,
                    "properties": properties,
                    "limit": limit,
                    "after": after or "0"
                }
            )
        else:
            response = self.client.crm.contacts.basic_api.get_page(
                limit=limit,
                after=after,
                properties=properties
            )
        
        results = []
        for contact in response.results:
            results.append({
                "id": contact.id,
                "firstname": contact.properties.get("firstname", ""),
                "lastname": contact.properties.get("lastname", ""),
                "company": contact.properties.get("company", ""),
            })
        
        return {
            "results": results,
            "paging": {
                "next": response.paging.next.after if response.paging and response.paging.next else None
            }
        }
    
    def iter_all_contacts(self, modified_after: Optional[str] = None) -> Iterator[dict]:
        """Iterate through all contacts with automatic pagination."""
        after = None
        while True:
            page = self.list_contacts(limit=100, after=after, modified_after=modified_after)
            
            for contact in page["results"]:
                yield contact
            
            after = page["paging"]["next"]
            if not after:
                break
    
    # ==========================================
    # ASSOCIATION OPERATIONS
    # ==========================================
    
    def create_signal_company_association(self, signal_id: str, company_id: str) -> bool:
        """Create an association between a Signal and a Company."""
        try:
            self.client.crm.associations.v4.basic_api.create(
                object_type=self.SIGNAL_OBJECT_TYPE,
                object_id=signal_id,
                to_object_type=self.COMPANY_OBJECT_TYPE,
                to_object_id=company_id,
                association_spec=[{
                    "associationCategory": "HUBSPOT_DEFINED",
                    "associationTypeId": self.SIGNAL_TO_COMPANY_ASSOCIATION
                }]
            )
            return True
        except Exception as e:
            print(f"Error creating Signal-Company association: {e}", flush=True)
            return False
    
    def create_signal_contact_association(self, signal_id: str, contact_id: str) -> bool:
        """Create an association between a Signal and a Contact."""
        if not self.SIGNAL_TO_CONTACT_ASSOCIATION:
            self._discover_association_types()
            
        if not self.SIGNAL_TO_CONTACT_ASSOCIATION:
            print("Warning: Signal-Contact association type not found", flush=True)
            return False
            
        try:
            self.client.crm.associations.v4.basic_api.create(
                object_type=self.SIGNAL_OBJECT_TYPE,
                object_id=signal_id,
                to_object_type=self.CONTACT_OBJECT_TYPE,
                to_object_id=contact_id,
                association_spec=[{
                    "associationCategory": "HUBSPOT_DEFINED", 
                    "associationTypeId": self.SIGNAL_TO_CONTACT_ASSOCIATION
                }]
            )
            return True
        except Exception as e:
            print(f"Error creating Signal-Contact association: {e}", flush=True)
            return False
    
    def get_company_count(self) -> int:
        """Get total number of companies in HubSpot."""
        response = self.client.crm.companies.search_api.do_search(
            public_object_search_request={
                "filterGroups": [],
                "limit": 1
            }
        )
        return response.total
    
    def get_contact_count(self) -> int:
        """Get total number of contacts in HubSpot."""
        response = self.client.crm.contacts.search_api.do_search(
            public_object_search_request={
                "filterGroups": [],
                "limit": 1
            }
        )
        return response.total
