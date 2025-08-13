#!/usr/bin/env python3
"""
CUIT Lookup GUI Application
Simple graphical interface for searching CUIT information
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import json
import csv
from datetime import datetime
from typing import List

try:
    from cuitonline_scraper import CUITOnlineScraper, CUITResult
except ImportError:
    print("Error: cuitonline_scraper module not found")
    print("Make sure cuitonline_scraper.py is in the same directory")
    exit(1)


class CUITLookupGUI:
    """GUI Application for CUIT lookups"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("CUIT Lookup Tool")
        self.root.geometry("800x600")
        
        # Initialize scraper with default method
        self.scraper = None
        self.current_results = []
        
        # Create GUI elements
        self.create_widgets()
        
        # Initialize scraper
        self.update_scraper_method()
    
    def create_widgets(self):
        """Create all GUI widgets"""
        
        # Top frame for search controls
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E))
        
        # Search input
        ttk.Label(top_frame, text="Search Name:").grid(row=0, column=0, padx=5)
        self.search_entry = ttk.Entry(top_frame, width=40)
        self.search_entry.grid(row=0, column=1, padx=5)
        self.search_entry.bind('<Return>', lambda e: self.search())
        
        # Search button
        self.search_button = ttk.Button(top_frame, text="Search", command=self.search)
        self.search_button.grid(row=0, column=2, padx=5)
        
        # Clear button
        ttk.Button(top_frame, text="Clear", command=self.clear_results).grid(row=0, column=3, padx=5)
        
        # Method selection
        ttk.Label(top_frame, text="Method:").grid(row=1, column=0, padx=5, pady=5)
        self.method_var = tk.StringVar(value="requests")
        method_combo = ttk.Combobox(top_frame, textvariable=self.method_var, 
                                   values=["requests", "selenium", "playwright"], 
                                   state="readonly", width=15)
        method_combo.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        method_combo.bind('<<ComboboxSelected>>', lambda e: self.update_scraper_method())
        
        # Status label
        self.status_label = ttk.Label(top_frame, text="Ready", foreground="green")
        self.status_label.grid(row=1, column=2, columnspan=2, padx=5, pady=5)
        
        # Results frame
        results_frame = ttk.LabelFrame(self.root, text="Results", padding="10")
        results_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=5)
        
        # Results text area
        self.results_text = scrolledtext.ScrolledText(results_frame, wrap=tk.WORD, width=80, height=20)
        self.results_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Results treeview (table)
        self.results_tree = ttk.Treeview(results_frame, columns=('CUIT', 'Name', 'Type', 'Status'), 
                                        show='headings', height=10)
        self.results_tree.heading('CUIT', text='CUIT')
        self.results_tree.heading('Name', text='Name')
        self.results_tree.heading('Type', text='Type')
        self.results_tree.heading('Status', text='Status')
        
        self.results_tree.column('CUIT', width=120)
        self.results_tree.column('Name', width=300)
        self.results_tree.column('Type', width=150)
        self.results_tree.column('Status', width=100)
        
        self.results_tree.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        
        # Scrollbar for treeview
        tree_scroll = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        tree_scroll.grid(row=1, column=1, sticky=(tk.N, tk.S))
        self.results_tree.configure(yscrollcommand=tree_scroll.set)
        
        # Double-click to show details
        self.results_tree.bind('<Double-Button-1>', self.show_details)
        
        # Bottom frame for export buttons
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E))
        
        ttk.Button(bottom_frame, text="Export to CSV", command=self.export_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Export to JSON", command=self.export_json).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Batch Search", command=self.batch_search).pack(side=tk.LEFT, padx=5)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        results_frame.rowconfigure(1, weight=1)
    
    def update_scraper_method(self):
        """Update the scraper with selected method"""
        method = self.method_var.get()
        try:
            self.scraper = CUITOnlineScraper(method=method, headless=True)
            self.status_label.config(text=f"Using {method} method", foreground="green")
        except Exception as e:
            self.status_label.config(text=f"Error: {str(e)}", foreground="red")
            messagebox.showerror("Error", f"Failed to initialize {method} scraper:\n{str(e)}")
    
    def search(self):
        """Perform CUIT search"""
        search_term = self.search_entry.get().strip()
        
        if not search_term:
            messagebox.showwarning("Warning", "Please enter a search term")
            return
        
        # Disable search button during search
        self.search_button.config(state='disabled')
        self.status_label.config(text="Searching...", foreground="blue")
        
        # Clear previous results
        self.clear_results()
        
        # Run search in separate thread
        thread = threading.Thread(target=self._search_thread, args=(search_term,))
        thread.daemon = True
        thread.start()
    
    def _search_thread(self, search_term):
        """Search thread function"""
        try:
            results = self.scraper.search_by_name(search_term)
            
            # Update GUI in main thread
            self.root.after(0, self._update_results, results, search_term)
            
        except Exception as e:
            self.root.after(0, self._show_error, f"Search error: {str(e)}")
    
    def _update_results(self, results: List[CUITResult], search_term: str):
        """Update GUI with search results"""
        self.current_results = results
        
        if not results:
            self.results_text.insert(tk.END, f"No results found for '{search_term}'\n")
            self.status_label.config(text="No results found", foreground="orange")
        else:
            self.results_text.insert(tk.END, f"Found {len(results)} results for '{search_term}':\n\n")
            
            for i, result in enumerate(results, 1):
                # Add to text area
                self.results_text.insert(tk.END, f"Result {i}:\n")
                self.results_text.insert(tk.END, f"  CUIT: {result.cuit}\n")
                self.results_text.insert(tk.END, f"  Name: {result.name}\n")
                self.results_text.insert(tk.END, f"  Type: {result.tipo_persona}\n")
                self.results_text.insert(tk.END, f"  Status: {result.estado}\n")
                self.results_text.insert(tk.END, "-" * 50 + "\n")
                
                # Add to treeview
                self.results_tree.insert('', tk.END, values=(
                    result.cuit,
                    result.name,
                    result.tipo_persona,
                    result.estado
                ))
            
            self.status_label.config(text=f"Found {len(results)} results", foreground="green")
        
        # Re-enable search button
        self.search_button.config(state='normal')
    
    def _show_error(self, error_message: str):
        """Show error message"""
        self.status_label.config(text="Error", foreground="red")
        self.search_button.config(state='normal')
        messagebox.showerror("Error", error_message)
    
    def clear_results(self):
        """Clear all results"""
        self.results_text.delete(1.0, tk.END)
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.current_results = []
    
    def show_details(self, event):
        """Show detailed information for selected result"""
        selection = self.results_tree.selection()
        if not selection:
            return
        
        item = self.results_tree.item(selection[0])
        values = item['values']
        
        # Find corresponding result
        for result in self.current_results:
            if result.cuit == values[0]:
                # Create details window
                details_window = tk.Toplevel(self.root)
                details_window.title(f"Details for {result.cuit}")
                details_window.geometry("500x400")
                
                # Details text
                details_text = scrolledtext.ScrolledText(details_window, wrap=tk.WORD, width=60, height=20)
                details_text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
                
                # Add details
                details_text.insert(tk.END, f"CUIT: {result.cuit}\n")
                details_text.insert(tk.END, f"Name: {result.name}\n")
                details_text.insert(tk.END, f"Type: {result.tipo_persona}\n")
                details_text.insert(tk.END, f"Status: {result.estado}\n")
                
                if result.direccion:
                    details_text.insert(tk.END, f"Address: {result.direccion}\n")
                if result.localidad:
                    details_text.insert(tk.END, f"City: {result.localidad}\n")
                if result.provincia:
                    details_text.insert(tk.END, f"Province: {result.provincia}\n")
                if result.condicion_impositiva:
                    details_text.insert(tk.END, f"Tax Status: {result.condicion_impositiva}\n")
                if result.actividades:
                    details_text.insert(tk.END, "\nActivities:\n")
                    for activity in result.actividades:
                        details_text.insert(tk.END, f"  - {activity}\n")
                
                if result.detail_url:
                    details_text.insert(tk.END, f"\nDetail URL: {result.detail_url}\n")
                
                details_text.config(state='disabled')
                break
    
    def export_csv(self):
        """Export results to CSV"""
        if not self.current_results:
            messagebox.showwarning("Warning", "No results to export")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"cuit_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        
        if filename:
            try:
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['CUIT', 'Name', 'Type', 'Status', 'Address', 'City', 'Province'])
                    
                    for result in self.current_results:
                        writer.writerow([
                            result.cuit,
                            result.name,
                            result.tipo_persona,
                            result.estado,
                            result.direccion or '',
                            result.localidad or '',
                            result.provincia or ''
                        ])
                
                messagebox.showinfo("Success", f"Results exported to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export: {str(e)}")
    
    def export_json(self):
        """Export results to JSON"""
        if not self.current_results:
            messagebox.showwarning("Warning", "No results to export")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"cuit_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        
        if filename:
            try:
                data = []
                for result in self.current_results:
                    data.append({
                        'cuit': result.cuit,
                        'name': result.name,
                        'tipo_persona': result.tipo_persona,
                        'estado': result.estado,
                        'direccion': result.direccion,
                        'localidad': result.localidad,
                        'provincia': result.provincia,
                        'condicion_impositiva': result.condicion_impositiva,
                        'actividades': result.actividades
                    })
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                messagebox.showinfo("Success", f"Results exported to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export: {str(e)}")
    
    def batch_search(self):
        """Open batch search dialog"""
        batch_window = tk.Toplevel(self.root)
        batch_window.title("Batch Search")
        batch_window.geometry("500x400")
        
        # Instructions
        ttk.Label(batch_window, text="Enter names to search (one per line):").pack(padx=10, pady=5)
        
        # Text area for names
        names_text = scrolledtext.ScrolledText(batch_window, wrap=tk.WORD, width=60, height=15)
        names_text.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        
        # Buttons frame
        button_frame = ttk.Frame(batch_window)
        button_frame.pack(pady=10)
        
        def run_batch():
            names = names_text.get(1.0, tk.END).strip().split('\n')
            names = [n.strip() for n in names if n.strip()]
            
            if not names:
                messagebox.showwarning("Warning", "No names to search")
                return
            
            batch_window.destroy()
            
            # Clear current results
            self.clear_results()
            
            # Run batch search
            self.status_label.config(text="Running batch search...", foreground="blue")
            thread = threading.Thread(target=self._batch_search_thread, args=(names,))
            thread.daemon = True
            thread.start()
        
        ttk.Button(button_frame, text="Search", command=run_batch).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=batch_window.destroy).pack(side=tk.LEFT, padx=5)
    
    def _batch_search_thread(self, names: List[str]):
        """Batch search thread"""
        all_results = []
        
        for i, name in enumerate(names, 1):
            try:
                self.root.after(0, lambda: self.status_label.config(
                    text=f"Searching {i}/{len(names)}: {name}", foreground="blue"))
                
                results = self.scraper.search_by_name(name)
                all_results.extend(results)
                
                # Update GUI with progress
                self.root.after(0, self._update_batch_progress, i, len(names), name, len(results))
                
            except Exception as e:
                self.root.after(0, lambda: self.results_text.insert(
                    tk.END, f"Error searching '{name}': {str(e)}\n"))
        
        # Final update
        self.root.after(0, self._update_results, all_results, "Batch search")


    def _update_batch_progress(self, current: int, total: int, name: str, found: int):
        """Update batch search progress"""
        self.results_text.insert(tk.END, f"[{current}/{total}] {name}: {found} results\n")
        self.results_text.see(tk.END)


def main():
    """Main function"""
    root = tk.Tk()
    app = CUITLookupGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()