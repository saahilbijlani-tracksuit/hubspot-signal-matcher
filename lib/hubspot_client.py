"""
HubSpot API Client

Handles all interactions with HubSpot CRM:
- Fetching Signals, Companies, and Contacts
- Creating associations between objects
- Pagination for bulk operations
"""

import os
import requests
from typing import Optional, Iterator
from hubspot import HubSpot
from hubspot.crm.objects import SimplePublicObjectInput
from hubspot.crm.associations.v4 import BatchInputPublicDefaultAssociationMultiPost


class HubSpotClient:
    """Client for HubSpot CRM operations."""
    
    # Custom object type IDs (for SDK calls)
    SIGNAL_OBJECT_TYPE = "2-54609655"
    COMPANY_OBJECT_TYPE = "0-2"
    CONTACT_OBJECT_TYPE = "0-1"
    
    # Object names (for REST API URL paths)
    # REST API requires object NAMES, not numeric IDs
    SIGNAL_OBJECT_NAME = "signals"  # Custom object schema name
    COMPANY_OBJECT_NAME = "companies"
    CONTACT_OBJECT_NAME = "contacts"
    
    # Association type IDs (Signal <-> Company/Contact)
    SIGNAL_TO_COMPANY_ASSOCIATION = 421
    SIGNAL_TO_CONTACT_ASSOCIATION = None  # Will be discovered
    
    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize HubSpot client.
        
        Args:
            access_token: HubSpot Private App access token.
                         Falls back to HUBSPOT_ACCESS_TOKEN env var.
        """
        self.access_token = access_token or os.environ.get("HUBSPOT_ACCESS_TOKEN")
        if not self.access_token:
            raise ValueError("HubSpot access token required")
        
        self.client = HubSpot(access_token=self.access_token)
        
        # Discover association type for Signal -> Contact
        self._discover_association_types()
    
    def _discover_association_types(self):
        """Discover association type IDs between Signals and other objects."""
        try:
            # Get Signal -> Contact association type
            response = self.client.crm.associations.v4.schema.definitions_api.get_all(
                from_object_type=self.SIGNAL_OBJECT_TYPE,
                to_object_type=self.CONTACT_OBJECT_TYPE
            )
            if response.results:
                self.SIGNAL_TO_CONTACT_ASSOCIATION = response.results[0].type_id
        except Exception as e:
            print(f"Warning: Could not discover association types: {e}")
            # Fallback - will try to discover when needed
    
    # ==========================================
    # SIGNAL OPERATIONS
    # ==========================================
    
    def get_signal(self, signal_id: str) -> dict:
        """
        Fetch a Signal by ID with all relevant properties.
        
        Args:
            signal_id: HubSpot object ID of the Signal
            
        Returns:
            Signal data with properties
        """
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
        """
        List signals with pagination.
        
        Args:
            limit: Number of signals per page (max 100)
            after: Pagination cursor
            
        Returns:
            Dict with 'results' and 'paging' info
        """
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
        """
        List signals that don't have company or contact associations.
        
        Args:
            limit: Maximum number of signals to return
            
        Returns:
            List of signal dicts without associations
        """
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
        """
        List companies with pagination.
        
        Args:
            limit: Number of companies per page (max 100)
            after: Pagination cursor
            modified_after: ISO timestamp to filter by modification date
            
        Returns:
            Dict with 'results' and 'paging' info
        """
        properties = ["name", "domain", "hs_lastmodifieddate"]
        
        if modified_after:
            # Use search API for filtering by date
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
        """
        Iterate through all companies with automatic pagination.
        
        Args:
            modified_after: ISO timestamp to filter by modification date
            
        Yields:
            Company dictionaries
        """
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
        """
        List contacts with pagination.
        
        Args:
            limit: Number of contacts per page (max 100)
            after: Pagination cursor
            modified_after: ISO timestamp to filter by modification date
            
        Returns:
            Dict with 'results' and 'paging' info
        """
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
        """
        Iterate through all contacts with automatic pagination.
        
        Args:
            modified_after: ISO timestamp to filter by modification date
            
        Yields:
            Contact dictionaries
        """
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
        """
        Create an association between a Signal and a Company.
        
        Args:
            signal_id: HubSpot ID of the Signal
            company_id: HubSpot ID of the Company
            
        Returns:
            True if successful
        """
        try:
            # Use direct API call for custom object associations
            # REST API requires object NAMES in URL path, not numeric type IDs
            url = f"https://api.hubapi.com/crm/v4/objects/{self.SIGNAL_OBJECT_NAME}/{signal_id}/associations/{self.COMPANY_OBJECT_NAME}/{company_id}"
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            payload = [{
                "associationCategory": "HUBSPOT_DEFINED",
                "associationTypeId": self.SIGNAL_TO_COMPANY_ASSOCIATION
            }]
            
            response = requests.put(url, headers=headers, json=payload)
            
            if response.status_code in [200, 201]:
                return True
            else:
                print(f"Error creating Signal-Company association: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Error creating Signal-Company association: {e}")
            return False
    
    def create_signal_contact_association(self, signal_id: str, contact_id: str) -> bool:
        """
        Create an association between a Signal and a Contact.
        
        Args:
            signal_id: HubSpot ID of the Signal
            contact_id: HubSpot ID of the Contact
            
        Returns:
            True if successful
        """
        if not self.SIGNAL_TO_CONTACT_ASSOCIATION:
            # Try to discover if not already known
            self._discover_association_types()
            
        if not self.SIGNAL_TO_CONTACT_ASSOCIATION:
            print("Warning: Signal-Contact association type not found")
            return False
            
        try:
            # Use direct API call for custom object associations
            # REST API requires object NAMES in URL path, not numeric type IDs
            url = f"https://api.hubapi.com/crm/v4/objects/{self.SIGNAL_OBJECT_NAME}/{signal_id}/associations/{self.CONTACT_OBJECT_NAME}/{contact_id}"
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            payload = [{
                "associationCategory": "HUBSPOT_DEFINED",
                "associationTypeId": self.SIGNAL_TO_CONTACT_ASSOCIATION
            }]
            
            response = requests.put(url, headers=headers, json=payload)
            
            if response.status_code in [200, 201]:
                return True
            else:
                print(f"Error creating Signal-Contact association: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Error creating Signal-Contact association: {e}")
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
