# Copyright (c) 2026, Nick Aldewereld, NIXPAY B.V.
# License: AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html)
# For commercial licensing, contact: nick@nixpay.nl

import frappe
from frappe import _


@frappe.whitelist()
def create_offerte(offerte_data):
    """
    Create a new NixFact Offerte
    
    Args:
        offerte_data (dict): Dictionary containing offerte data
            - offerte_nr (str): Offerte number
            - klant (str): Customer ID
            - bedrag_excl (float): Amount excluding VAT
            - bedrag_incl (float): Amount including VAT
            - offerte_datum (str): Offerte date (YYYY-MM-DD)
            - referentie (str, optional): Reference
            - status (str, optional): Status (Geaccepteerd/Geweigerd/Factuur aangemaakt)
    
    Returns:
        dict: Created offerte document
    """
    
    # Validate required fields
    required_fields = ['offerte_nr', 'klant', 'bedrag_excl', 'bedrag_incl', 'offerte_datum']
    for field in required_fields:
        if field not in offerte_data:
            frappe.throw(f"Field '{field}' is required")
    
    # Set default status if not provided
    if 'status' not in offerte_data:
        offerte_data['status'] = 'Geaccepteerd'
    
    # Create the offerte document
    try:
        offerte = frappe.get_doc({
            'doctype': 'NixFact Offerte',
            'offerte_nr': offerte_data['offerte_nr'],
            'klant': offerte_data['klant'],
            'bedrag_excl': offerte_data['bedrag_excl'],
            'bedrag_incl': offerte_data['bedrag_incl'],
            'offerte_datum': offerte_data['offerte_datum'],
            'referentie': offerte_data.get('referentie', ''),
            'status': offerte_data['status']
        })
        
        offerte.insert(ignore_permissions=True)
        
        return {
            'success': True,
            'message': 'Offerte created successfully',
            'offerte_id': offerte.name,
            'offerte_nr': offerte.offerte_nr
        }
        
    except Exception as e:
        frappe.log_error(f"Error creating NixFact Offerte: {str(e)}", _("NixFact Offerte Creation Error"))
        frappe.throw(f"Failed to create offerte: {str(e)}")


@frappe.whitelist()
def get_offerte(offerte_id):
    """
    Get NixFact Offerte by ID
    
    Args:
        offerte_id (str): Offerte document name
    
    Returns:
        dict: Offerte document data
    """
    try:
        offerte = frappe.get_doc('NixFact Offerte', offerte_id)
        return {
            'success': True,
            'data': {
                'offerte_id': offerte.name,
                'offerte_nr': offerte.offerte_nr,
                'klant': offerte.klant,
                'bedrag_excl': offerte.bedrag_excl,
                'bedrag_incl': offerte.bedrag_incl,
                'offerte_datum': offerte.offerte_datum,
                'referentie': offerte.referentie,
                'status': offerte.status,
                'creation': offerte.creation,
                'modified': offerte.modified
            }
        }
    except frappe.DoesNotExistError:
        frappe.throw(f"Offerte {offerte_id} not found")
    except Exception as e:
        frappe.log_error(f"Error retrieving NixFact Offerte {offerte_id}: {str(e)}", _("NixFact Offerte Retrieval Error"))
        frappe.throw(f"Failed to retrieve offerte: {str(e)}")


@frappe.whitelist()
def update_offerte_status(offerte_id, status):
    """
    Update status of NixFact Offerte
    
    Args:
        offerte_id (str): Offerte document name
        status (str): New status (Geaccepteerd/Geweigerd/Factuur aangemaakt)
    
    Returns:
        dict: Update result
    """
    valid_statuses = ['Geaccepteerd', 'Geweigerd', 'Factuur aangemaakt']
    
    if status not in valid_statuses:
        frappe.throw(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
    
    try:
        offerte = frappe.get_doc('NixFact Offerte', offerte_id)
        offerte.status = status
        offerte.save(ignore_permissions=True)
        
        return {
            'success': True,
            'message': f'Offerte status updated to {status}',
            'offerte_id': offerte.name,
            'new_status': offerte.status
        }
    except frappe.DoesNotExistError:
        frappe.throw(f"Offerte {offerte_id} not found")
    except Exception as e:
        frappe.log_error(f"Error updating NixFact Offerte {offerte_id} status: {str(e)}", _("NixFact Offerte Update Error"))
        frappe.throw(f"Failed to update offerte status: {str(e)}")