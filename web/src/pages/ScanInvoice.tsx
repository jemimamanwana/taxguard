import { Card } from '../components/ui'
import InvoiceScanner from '../components/InvoiceScanner'

export default function ScanInvoice() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Smart invoice capture</h1>
        <p className="text-sm text-muted max-w-3xl">Photograph a tax invoice instead of typing it. Fields are read automatically with a confidence score; only
          low-confidence fields need a human check. Every invoice is checked against the VAT register, the supplier’s own declarations and all stored invoices.</p>
      </div>
      <Card><InvoiceScanner /></Card>
    </div>
  )
}
