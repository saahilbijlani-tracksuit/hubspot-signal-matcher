"""HubSpot API Client

Handles all interactions with HubSpot CRM:
- Fetching Signals, Companies, and Contacts
- Creating associations between objects
- Pagination for bulk operations
"""

import os
import requests
from typing import Optional, Iterator, List
from hubspot import HubSpot
from hubspot.crm.objects import SimplePublicObjectInput
from hubspot.crm.associations.v4 import BatchInputPublicDefaultAssociationMultiPost


class HubSpotClient:
    SIGNAL_OBJECT_TYPE = "2-54609655"
    COMPANY_OBJECT_TYPE = "0-2"
    CONTACT_OBJECT_TYPE = "0-1"
    SIGNAL_OBJECT_TYPE_API = "2-54609655"
    COMPANY_OBJECT_TYPE_API = "companies"
    CONTACT_OBJECT_TYPE_API = "contacts"
    SIGNAL_TO_COMPANY_ASSOCIATION = 421
    SIGNAL_TO_CONTACT_ASSOCIATION = None

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.environ.get("HUBSPOT_ACCESS_TOKEN")
        if not self.access_token:
            raise ValueError("HubSpot access token required")
        self.client = HubSpot(access_token=self.access_token)
        self._discover_association_types()

    def _discover_association_types(self):
        try:
            response = self.client.crm.associations.v4.schema.definitions_api.get_all(
                from_object_type=self.SIGNAL_OBJECT_TYPE, to_object_type=self.CONTACT_OBJECT_TYPE)
            if response.results:
                self.SIGNAL_TO_CONTACT_ASSOCIATION = response.results[0].type_id
        except Exception as e:
            print(f"Warning: Could not discover association types: {e}")

    def get_signal(self, signal_id: str) -> dict:
        properties = ["signal_name", "signal_description", "signal_citation", "signal_type", "signal_status", "signal_origin", "signal_weighting"]
        response = self.client.crm.objects.basic_api.get_by_id(
            object_type=self.SIGNAL_OBJECT_TYPE, object_id=signal_id, properties=properties,
            associations=[self.COMPANY_OBJECT_TYPE, self.CONTACT_OBJECT_TYPE])
        return {"id": response.id, "properties": response.properties, "associations": self._parse_associations(response.associations)}

    def _parse_associations(self, associations) -> dict:
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
        properties = ["signal_name", "signal_description", "signal_citation", "signal_type", "signal_status"]
        response = self.client.crm.objects.basic_api.get_page(
            object_type=self.SIGNAL_OBJECT_TYPE, limit=limit, after=after, properties=properties,
            associations=[self.COMPANY_OBJECT_TYPE, self.CONTACT_OBJECT_TYPE])
        results = [{"id": s.id, "properties": s.properties, "associations": self._parse_associations(s.associations)} for s in response.results]
        return {"results": results, "paging": {"next": response.paging.next.after if response.paging and response.paging.next else None}}

    def list_signals_without_associations(self, limit: int = 100) -> list:
        unassociated, after = [], None
        while len(unassociated) < limit:
            page = self.list_signals(limit=min(100, limit - len(unassociated)), after=after)
            for signal in page["results"]:
                assoc = signal.get("associations", {})
                if not assoc.get("companies", []) and not assoc.get("contacts", []):
                    unassociated.append(signal)
                    if len(unassociated) >= limit:
                        break
            after = page["paging"]["next"]
            if not after:
                break
        return unassociated

    def get_company(self, company_id: str) -> dict:
        response = self.client.crm.companies.basic_api.get_by_id(company_id=company_id, properties=["name", "domain"])
        return {"id": response.id, "name": response.properties.get("name", ""), "domain": response.properties.get("domain", "")}

    def list_companies(self, limit: int = 100, after: Optional[str] = None, modified_after: Optional[str] = None) -> dict:
        properties = ["name", "domain", "hs_lastmodifieddate"]
        if modified_after:
            filter_groups = [{"filters": [{"propertyName": "hs_lastmodifieddate", "operator": "GTE", "value": modified_after}]}]
            response = self.client.crm.companies.search_api.do_search(public_object_search_request={"filterGroups": filter_groups, "properties": properties, "limit": limit, "after": after or "0"})
        else:
            response = self.client.crm.companies.basic_api.get_page(limit=limit, after=after, properties=properties)
        results = [{"id": c.id, "name": c.properties.get("name", ""), "domain": c.properties.get("domain", "")} for c in response.results]
        return {"results": results, "paging": {"next": response.paging.next.after if response.paging and response.paging.next else None}}

    def iter_all_companies(self, modified_after: Optional[str] = None) -> Iterator[dict]:
        after = None
        while True:
            page = self.list_companies(limit=100, after=after, modified_after=modified_after)
            for company in page["results"]:
                yield company
            after = page["paging"]["next"]
            if not after:
                break

    def get_contact(self, contact_id: str) -> dict:
        response = self.client.crm.contacts.basic_api.get_by_id(contact_id=contact_id, properties=["firstname", "lastname", "company"])
        return {"id": response.id, "firstname": response.properties.get("firstname", ""), "lastname": response.properties.get("lastname", ""), "company": response.properties.get("company", "")}

    def list_contacts(self, limit: int = 100, after: Optional[str] = None, modified_after: Optional[str] = None) -> dict:
        properties = ["firstname", "lastname", "company", "hs_lastmodifieddate"]
        if modified_after:
            filter_groups = [{"filters": [{"propertyName": "hs_lastmodifieddate", "operator": "GTE", "value": modified_after}]}]
            response = self.client.crm.contacts.search_api.do_search(public_object_search_request={"filterGroups": filter_groups, "properties": properties, "limit": limit, "after": after or "0"})
        else:
            response = self.client.crm.contacts.basic_api.get_page(limit=limit, after=after, properties=properties)
        results = [{"id": c.id, "firstname": c.properties.get("firstname", ""), "lastname": c.properties.get("lastname", ""), "company": c.properties.get("company", "")} for c in response.results]
        return {"results": results, "paging": {"next": response.paging.next.after if response.paging and response.paging.next else None}}

    def iter_all_contacts(self, modified_after: Optional[str] = None) -> Iterator[dict]:
        after = None
        while True:
            page = self.list_contacts(limit=100, after=after, modified_after=modified_after)
            for contact in page["results"]:
                yield contact
            after = page["paging"]["next"]
            if not after:
                break

    def create_signal_company_association(self, signal_id: str, company_id: str) -> bool:
        try:
            url = f"https://api.hubapi.com/crm/v4/objects/{self.SIGNAL_OBJECT_TYPE_API}/{signal_id}/associations/{self.COMPANY_OBJECT_TYPE_API}/{company_id}"
            headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
            payload = [{"associationCategory": "USER_DEFINED", "associationTypeId": self.SIGNAL_TO_COMPANY_ASSOCIATION}]
            response = requests.put(url, headers=headers, json=payload)
            if response.status_code in [200, 201]:
                return True
            print(f"Error creating Signal-Company association: {response.status_code} - {response.text}")
            return False
        except Exception as e:
            print(f"Error creating Signal-Company association: {e}")
            return False

    def create_signal_contact_association(self, signal_id: str, contact_id: str) -> bool:
        if not self.SIGNAL_TO_CONTACT_ASSOCIATION:
            self._discover_association_types()
        if not self.SIGNAL_TO_CONTACT_ASSOCIATION:
            print("Warning: Signal-Contact association type not found")
            return False
        try:
            url = f"https://api.hubapi.com/crm/v4/objects/{self.SIGNAL_OBJECT_TYPE_API}/{signal_id}/associations/{self.CONTACT_OBJECT_TYPE_API}/{contact_id}"
            headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
            payload = [{"associationCategory": "USER_DEFINED", "associationTypeId": self.SIGNAL_TO_CONTACT_ASSOCIATION}]
            response = requests.put(url, headers=headers, json=payload)
            if response.status_code in [200, 201]:
                return True
            print(f"Error creating Signal-Contact association: {response.status_code} - {response.text}")
            return False
        except Exception as e:
            print(f"Error creating Signal-Contact association: {e}")
            return False

    def get_company_count(self) -> int:
        return self.client.crm.companies.search_api.do_search(public_object_search_request={"filterGroups": [], "limit": 1}).total

    def get_contact_count(self) -> int:
        return self.client.crm.contacts.search_api.do_search(public_object_search_request={"filterGroups": [], "limit": 1}).total

    def get_company_details(self, company_id: str) -> dict:
        properties = ["name", "domain", "lifecyclestage", "company_type", "ae_owner", "sdr_owner", "brand_champ", "hubspot_owner_id"]
        try:
            response = self.client.crm.companies.basic_api.get_by_id(company_id=company_id, properties=properties)
            return {
                "id": response.id, "name": response.properties.get("name", ""), "domain": response.properties.get("domain", ""),
                "lifecyclestage": response.properties.get("lifecyclestage", ""), "company_type": response.properties.get("company_type", ""),
                "ae_owner": response.properties.get("ae_owner", ""), "sdr_owner": response.properties.get("sdr_owner", ""),
                "brand_champ": response.properties.get("brand_champ", ""), "hubspot_owner_id": response.properties.get("hubspot_owner_id", "")}
        except Exception as e:
            print(f"Error fetching company details: {e}")
            return {}

    def get_owner_name(self, owner_id: str) -> str:
        if not owner_id:
            return ""
        try:
            response = self.client.crm.owners.owners_api.get_by_id(owner_id=int(owner_id))
            return f"{response.first_name or ''} {response.last_name or ''}".strip()
        except Exception as e:
            print(f"Error fetching owner name: {e}")
            return ""

    def get_owner_email(self, owner_id: str) -> str:
        if not owner_id:
            return ""
        try:
            response = self.client.crm.owners.owners_api.get_by_id(owner_id=int(owner_id))
            return response.email or ""
        except Exception as e:
            print(f"Error fetching owner email: {e}")
            return ""

    def update_signal_owner(self, signal_id: str, owner_id: str) -> bool:
        if not owner_id:
            print("Warning: No owner ID provided")
            return False
        try:
            url = f"https://api.hubapi.com/crm/v3/objects/{self.SIGNAL_OBJECT_TYPE}/{signal_id}"
            headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
            payload = {"properties": {"hubspot_owner_id": str(owner_id)}}
            response = requests.patch(url, headers=headers, json=payload)
            if response.status_code == 200:
                return True
            print(f"Error updating signal owner: {response.status_code} - {response.text}")
            return False
        except Exception as e:
            print(f"Error updating signal owner: {e}")
            return False

    def update_signal_shared_users(self, signal_id: str, user_ids: list) -> bool:
        if not user_ids:
            return True
        user_ids = [str(uid) for uid in user_ids if uid]
        if not user_ids:
            return True
        try:
            url = f"https://api.hubapi.com/crm/v3/objects/{self.SIGNAL_OBJECT_TYPE}/{signal_id}"
            headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
            payload = {"properties": {"hs_shared_user_ids": ";".join(user_ids)}}
            response = requests.patch(url, headers=headers, json=payload)
            if response.status_code == 200:
                return True
            print(f"Error updating signal shared users: {response.status_code} - {response.text}")
            return False
        except Exception as e:
            print(f"Error updating signal shared users: {e}")
            return False
