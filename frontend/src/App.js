import React, { useState, useEffect } from 'react';
import './App.css';
import axios from 'axios';
import { format, differenceInDays, parseISO } from 'date-fns';
import { Plus, Search, Calendar, AlertTriangle, Edit, Trash2, FileText, Sparkles, RotateCcw, Mail, Info, HelpCircle, Loader2, CheckCircle2, XCircle, AlertCircle } from 'lucide-react';
import { Button } from './components/ui/button';
import { Input } from './components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from './components/ui/dialog';
import { Label } from './components/ui/label';
import { Textarea } from './components/ui/textarea';
import { Alert, AlertDescription } from './components/ui/alert';
import { Badge } from './components/ui/badge';
import { Separator } from './components/ui/separator';
import { Toaster } from './components/ui/toaster';
import { useToast } from './hooks/use-toast';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './components/ui/tooltip';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Loading spinner component
const LoadingSpinner = ({ size = "sm" }) => (
  <Loader2 className={`animate-spin ${size === "sm" ? "h-4 w-4" : "h-6 w-6"}`} />
);

// Enhanced error boundary component
const ErrorDisplay = ({ error, onRetry }) => (
  <div className="text-center py-8">
    <XCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
    <h3 className="text-lg font-medium text-red-600 mb-2">Something went wrong</h3>
    <p className="text-sm text-slate-600 mb-4">{error}</p>
    {onRetry && (
      <Button onClick={onRetry} variant="outline" size="sm">
        Try Again
      </Button>
    )}
  </div>
);

function App() {
  const [contracts, setContracts] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isRenewalModalOpen, setIsRenewalModalOpen] = useState(false);
  const [currentContract, setCurrentContract] = useState(null);
  const [renewalContract, setRenewalContract] = useState(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState(null);
  const [documentText, setDocumentText] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [sendingReminders, setSendingReminders] = useState(false);
  const [formErrors, setFormErrors] = useState({});
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    client: '',
    contact_email: '',
    start_date: '',
    expiry_date: '',
    status: 'Active'
  });
  const [renewalData, setRenewalData] = useState({
    new_expiry_date: '',
    contact_email: ''
  });
  
  const { toast } = useToast();

  // Enhanced error handling for API calls
  const handleApiError = (error, defaultMessage = "An error occurred") => {
    console.error('API Error:', error);
    
    if (error.response) {
      // Server responded with error status
      const status = error.response.status;
      const message = error.response.data?.detail || error.response.data?.message || defaultMessage;
      
      if (status === 404) {
        return "Resource not found. Please refresh and try again.";
      } else if (status === 422) {
        return "Invalid data provided. Please check your input.";
      } else if (status >= 500) {
        return "Server error. Please try again later.";
      } else {
        return message;
      }
    } else if (error.request) {
      // Network error
      return "Network error. Please check your internet connection.";
    } else {
      return defaultMessage;
    }
  };

  // Enhanced fetch contracts with error handling
  const fetchContracts = async (showLoading = false) => {
    if (showLoading) setInitialLoading(true);
    setError(null);
    
    try {
      const response = await axios.get(`${API}/contracts`, {
        timeout: 10000, // 10 second timeout
      });
      setContracts(response.data);
      
      // Show onboarding if no contracts exist
      if (response.data.length === 0 && !localStorage.getItem('onboarding_seen')) {
        setShowOnboarding(true);
        localStorage.setItem('onboarding_seen', 'true');
      }
    } catch (error) {
      const errorMessage = handleApiError(error, "Failed to fetch contracts");
      setError(errorMessage);
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive"
      });
    } finally {
      setInitialLoading(false);
    }
  };

  useEffect(() => {
    fetchContracts(true);
  }, []);

  // Form validation
  const validateForm = (data) => {
    const errors = {};
    
    if (!data.name.trim()) errors.name = "Contract name is required";
    if (!data.client.trim()) errors.client = "Client name is required";
    if (!data.contact_email.trim()) {
      errors.contact_email = "Contact email is required";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.contact_email)) {
      errors.contact_email = "Please enter a valid email address";
    }
    if (!data.start_date) errors.start_date = "Start date is required";
    if (!data.expiry_date) errors.expiry_date = "Expiry date is required";
    
    // Date validation
    if (data.start_date && data.expiry_date) {
      const startDate = new Date(data.start_date);
      const expiryDate = new Date(data.expiry_date);
      
      if (expiryDate <= startDate) {
        errors.expiry_date = "Expiry date must be after start date";
      }
    }
    
    return errors;
  };

  // Filter contracts based on search term
  const filteredContracts = contracts.filter(contract =>
    contract.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    contract.client.toLowerCase().includes(searchTerm.toLowerCase()) ||
    contract.contact_email.toLowerCase().includes(searchTerm.toLowerCase())
  );

  // Get expiring contracts (within 30 days)
  const expiringContracts = contracts.filter(contract => {
    const daysUntilExpiry = differenceInDays(parseISO(contract.expiry_date), new Date());
    return daysUntilExpiry <= 30 && daysUntilExpiry >= 0;
  });

  // Calculate days until expiry
  const getDaysUntilExpiry = (expiryDate) => {
    const days = differenceInDays(parseISO(expiryDate), new Date());
    if (days < 0) return 'Expired';
    if (days === 0) return 'Expires Today';
    if (days === 1) return '1 day left';
    return `${days} days left`;
  };

  // Get status color
  const getStatusColor = (expiryDate, status) => {
    if (status === 'Expired') return 'bg-red-500';
    const days = differenceInDays(parseISO(expiryDate), new Date());
    if (days < 0) return 'bg-red-500';
    if (days <= 7) return 'bg-red-400';
    if (days <= 30) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  // Get card border class
  const getCardBorderClass = (expiryDate, status) => {
    if (status === 'Expired') return 'ring-2 ring-red-400 shadow-red-100';
    const days = differenceInDays(parseISO(expiryDate), new Date());
    if (days < 0) return 'ring-2 ring-red-400 shadow-red-100';
    if (days <= 30 && days >= 0) return 'ring-2 ring-yellow-400 shadow-yellow-100';
    return '';
  };

  // Enhanced form submission with validation
  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setFormErrors({});
    
    // Validate form
    const errors = validateForm(formData);
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      setLoading(false);
      toast({
        title: "Validation Error",
        description: "Please fix the errors in the form",
        variant: "destructive"
      });
      return;
    }
    
    try {
      if (currentContract) {
        await axios.put(`${API}/contracts/${currentContract.id}`, formData, {
          timeout: 10000
        });
        toast({
          title: "Success",
          description: "Contract updated successfully",
          action: <CheckCircle2 className="h-4 w-4" />
        });
      } else {
        await axios.post(`${API}/contracts`, formData, {
          timeout: 10000
        });
        toast({
          title: "Success", 
          description: "Contract created successfully",
          action: <CheckCircle2 className="h-4 w-4" />
        });
      }
      
      await fetchContracts();
      resetForm();
      setIsModalOpen(false);
    } catch (error) {
      const errorMessage = handleApiError(error, "Failed to save contract");
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive"
      });
    } finally {
      setLoading(false);
    }
  };

  // Enhanced contract renewal with validation
  const handleRenewalSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    // Validate renewal date
    if (!renewalData.new_expiry_date) {
      toast({
        title: "Validation Error",
        description: "Please select a new expiry date",
        variant: "destructive"
      });
      setLoading(false);
      return;
    }
    
    const newDate = new Date(renewalData.new_expiry_date);
    const today = new Date();
    if (newDate <= today) {
      toast({
        title: "Validation Error",
        description: "New expiry date must be in the future",
        variant: "destructive"
      });
      setLoading(false);
      return;
    }
    
    try {
      await axios.post(`${API}/contracts/${renewalContract.id}/renew`, renewalData, {
        timeout: 10000
      });
      toast({
        title: "Success",
        description: `Contract "${renewalContract.name}" renewed successfully`,
        action: <CheckCircle2 className="h-4 w-4" />
      });
      
      await fetchContracts();
      setIsRenewalModalOpen(false);
      setRenewalContract(null);
      setRenewalData({ new_expiry_date: '', contact_email: '' });
    } catch (error) {
      const errorMessage = handleApiError(error, "Failed to renew contract");
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive"
      });
    } finally {
      setLoading(false);
    }
  };

  // Enhanced delete with confirmation
  const handleDelete = async (contract) => {
    const confirmed = window.confirm(
      `Are you sure you want to delete "${contract.name}"? This action cannot be undone.`
    );
    if (!confirmed) return;
    
    try {
      await axios.delete(`${API}/contracts/${contract.id}`, {
        timeout: 10000
      });
      toast({
        title: "Success",
        description: `Contract "${contract.name}" deleted successfully`,
        action: <CheckCircle2 className="h-4 w-4" />
      });
      await fetchContracts();
    } catch (error) {
      const errorMessage = handleApiError(error, "Failed to delete contract");
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive"
      });
    }
  };

  // Handle edit
  const handleEdit = (contract) => {
    setCurrentContract(contract);
    setFormData({
      name: contract.name,
      client: contract.client,
      contact_email: contract.contact_email,
      start_date: contract.start_date,
      expiry_date: contract.expiry_date,
      status: contract.status
    });
    setFormErrors({});
    setIsModalOpen(true);
  };

  // Handle renewal
  const handleRenewal = (contract) => {
    setRenewalContract(contract);
    // Set new expiry date 1 year from today as default
    const nextYear = new Date();
    nextYear.setFullYear(nextYear.getFullYear() + 1);
    setRenewalData({
      new_expiry_date: nextYear.toISOString().split('T')[0],
      contact_email: contract.contact_email
    });
    setIsRenewalModalOpen(true);
  };

  // Reset form
  const resetForm = () => {
    setCurrentContract(null);
    setFormData({
      name: '',
      client: '',
      contact_email: '',
      start_date: '',
      expiry_date: '',
      status: 'Active'
    });
    setDocumentText('');
    setFormErrors({});
  };

  // Enhanced document analysis with better error handling
  const handleAnalyzeDocument = async () => {
    if (!documentText.trim()) {
      toast({
        title: "No Document Text",
        description: "Please paste contract text to analyze",
        variant: "destructive"
      });
      return;
    }

    if (documentText.length < 50) {
      toast({
        title: "Document Too Short",
        description: "Please provide more detailed contract text for better analysis",
        variant: "destructive"
      });
      return;
    }

    setAnalyzing(true);
    
    try {
      const response = await axios.post(`${API}/analyze-document`, {
        document_text: documentText
      }, {
        timeout: 30000 // 30 seconds for AI processing
      });
      
      const { contract_date, contract_tenure, expiry_date, error } = response.data;
      
      if (error) {
        toast({
          title: "Analysis Incomplete",
          description: error,
          variant: "destructive"
        });
      } else if (contract_date) {
        setFormData(prev => ({
          ...prev,
          start_date: contract_date,
          expiry_date: expiry_date || prev.expiry_date
        }));
        
        toast({
          title: "Analysis Complete",
          description: `Extracted: ${contract_date}${contract_tenure ? `, ${contract_tenure}` : ''}`,
          action: <CheckCircle2 className="h-4 w-4" />
        });
      } else {
        toast({
          title: "No Information Found",
          description: "Could not extract contract dates. Please enter manually.",
          variant: "destructive"
        });
      }
    } catch (error) {
      const errorMessage = handleApiError(error, "AI analysis failed");
      toast({
        title: "Analysis Error",
        description: errorMessage,
        variant: "destructive"
      });
    } finally {
      setAnalyzing(false);
    }
  };

  // Enhanced reminder trigger with feedback
  const triggerReminders = async () => {
    setSendingReminders(true);
    
    try {
      await axios.post(`${API}/send-reminders`, {}, {
        timeout: 15000
      });
      toast({
        title: "Reminders Sent",
        description: "Email reminders have been triggered for expiring contracts",
        action: <CheckCircle2 className="h-4 w-4" />
      });
    } catch (error) {
      const errorMessage = handleApiError(error, "Failed to send reminders");
      toast({
        title: "Error",
        description: errorMessage,
        variant: "destructive"
      });
    } finally {
      setSendingReminders(false);
    }
  };

  // Enhanced empty state component
  const EmptyState = () => (
    <div className="text-center py-16">
      <div className="mx-auto w-24 h-24 bg-blue-100 rounded-full flex items-center justify-center mb-6">
        <FileText className="h-12 w-12 text-blue-600" />
      </div>
      <h3 className="text-xl font-semibold text-slate-800 mb-2">
        {searchTerm ? 'No contracts found' : 'Welcome to KrijoTech Contract Management'}
      </h3>
      <p className="text-slate-600 mb-6 max-w-md mx-auto leading-relaxed">
        {searchTerm 
          ? `No contracts match "${searchTerm}". Try adjusting your search terms or check the spelling.`
          : 'Get started by creating your first contract. Use AI-powered document analysis to extract dates automatically and never miss renewal deadlines again.'
        }
      </p>
      {!searchTerm && (
        <div className="space-y-4">
          <Button 
            onClick={() => {resetForm(); setIsModalOpen(true);}} 
            className="bg-blue-600 hover:bg-blue-700 px-6 py-3"
            size="lg"
          >
            <Plus className="h-5 w-5 mr-2" />
            Create Your First Contract
          </Button>
          <p className="text-sm text-slate-500">
            💡 Tip: Try the AI document analysis feature to automatically extract contract dates
          </p>
        </div>
      )}
    </div>
  );

  // Loading state
  if (initialLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center">
        <div className="text-center">
          <LoadingSpinner size="lg" />
          <p className="mt-4 text-slate-600">Loading your contracts...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error && contracts.length === 0) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center">
        <ErrorDisplay error={error} onRetry={() => fetchContracts(true)} />
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
        <div className="container mx-auto px-4 py-8">
          {/* Enhanced Header */}
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                <FileText className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-4xl font-bold text-slate-800">Corvus Contract Management System</h1>
                <p className="text-slate-600">AI-powered contract management with automated email reminders</p>
              </div>
            </div>
            <div className="flex items-center gap-4 text-sm text-slate-500">
              <span className="flex items-center gap-1">
                <CheckCircle2 className="h-4 w-4 text-green-500" />
                {contracts.length} Total Contracts
              </span>
              <span className="flex items-center gap-1">
                <AlertCircle className="h-4 w-4 text-yellow-500" />
                {expiringContracts.length} Expiring Soon
              </span>
            </div>
          </div>

          {/* Onboarding Banner */}
          {showOnboarding && contracts.length === 0 && (
            <Alert className="mb-6 border-blue-200 bg-blue-50">
              <Info className="h-4 w-4 text-blue-600" />
              <AlertDescription className="text-blue-800">
                <strong>Welcome!</strong> Start by creating your first contract. Use the AI document analysis feature to automatically extract contract dates from your documents.
                <Button 
                  variant="link" 
                  size="sm" 
                  onClick={() => setShowOnboarding(false)}
                  className="ml-2 h-auto p-0 text-blue-600"
                >
                  Dismiss
                </Button>
              </AlertDescription>
            </Alert>
          )}

          {/* Expiring Contracts Alert */}
          {expiringContracts.length > 0 && (
            <Alert className="mb-6 border-yellow-500 bg-yellow-50">
              <AlertTriangle className="h-4 w-4 text-yellow-600" />
              <AlertDescription className="text-yellow-800">
                <strong>⚠️ {expiringContracts.length} contract{expiringContracts.length > 1 ? 's' : ''} expiring soon:</strong>{' '}
                {expiringContracts.map(c => c.name).join(', ')}
                <Button 
                  variant="link" 
                  size="sm" 
                  onClick={triggerReminders}
                  className="ml-2 h-auto p-0 text-yellow-800 hover:text-yellow-900"
                  disabled={sendingReminders}
                >
                  {sendingReminders ? <LoadingSpinner /> : "Send Reminders Now"}
                </Button>
              </AlertDescription>
            </Alert>
          )}

          {/* Enhanced Controls */}
          <div className="flex flex-col sm:flex-row gap-4 mb-6">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400 h-4 w-4" />
              <Input
                placeholder="Search by contract name, client, or email address..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 h-11"
              />
              {searchTerm && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setSearchTerm('')}
                  className="absolute right-2 top-1/2 transform -translate-y-1/2 h-7 w-7 p-0"
                >
                  <XCircle className="h-4 w-4" />
                </Button>
              )}
            </div>
            
            <div className="flex gap-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button 
                    onClick={triggerReminders} 
                    variant="outline"
                    disabled={sendingReminders}
                    className="h-11"
                  >
                    {sendingReminders ? <LoadingSpinner /> : <Mail className="h-4 w-4 mr-2" />}
                    Send Reminders
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Manually trigger email reminders for expiring contracts</p>
                </TooltipContent>
              </Tooltip>
              
              <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
                <DialogTrigger asChild>
                  <Button onClick={resetForm} className="bg-blue-600 hover:bg-blue-700 h-11">
                    <Plus className="h-4 w-4 mr-2" />
                    Add Contract
                  </Button>
                </DialogTrigger>
                
                <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
                  <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                      {currentContract ? <Edit className="h-5 w-5" /> : <Plus className="h-5 w-5" />}
                      {currentContract ? 'Edit Contract' : 'Create New Contract'}
                    </DialogTitle>
                  </DialogHeader>
                  
                  <form onSubmit={handleSubmit} className="space-y-6">
                    {/* Enhanced AI Document Analysis Section */}
                    <div className="bg-gradient-to-r from-blue-50 to-indigo-50 p-6 rounded-lg border border-blue-200">
                      <div className="flex items-center gap-3 mb-4">
                        <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center">
                          <Sparkles className="h-4 w-4 text-white" />
                        </div>
                        <div>
                          <h3 className="font-semibold text-blue-900">AI Document Analysis</h3>
                          <p className="text-sm text-blue-700">Extract contract dates automatically from your documents</p>
                        </div>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="h-4 w-4 text-blue-600 cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent className="max-w-sm">
                            <p>Paste your contract text here and our AI will automatically extract the start date and contract duration to calculate the expiry date.</p>
                          </TooltipContent>
                        </Tooltip>
                      </div>
                      
                      <div className="space-y-4">
                        <div>
                          <Label htmlFor="document-text" className="text-sm font-medium text-slate-700">
                            Contract Document Text
                          </Label>
                          <Textarea
                            id="document-text"
                            placeholder="Paste your contract text here. Include details like 'This agreement is effective from January 15, 2024, for a period of 12 months...'"
                            value={documentText}
                            onChange={(e) => setDocumentText(e.target.value)}
                            rows={4}
                            className="resize-none mt-1"
                          />
                          <p className="text-xs text-slate-500 mt-1">
                            💡 Tip: Include sentences that mention dates and contract duration for best results
                          </p>
                        </div>
                        <Button
                          type="button"
                          onClick={handleAnalyzeDocument}
                          disabled={analyzing || !documentText.trim()}
                          variant="outline"
                          className="w-full"
                        >
                          {analyzing ? (
                            <>
                              <LoadingSpinner />
                              <span className="ml-2">Analyzing with AI...</span>
                            </>
                          ) : (
                            <>
                              <FileText className="h-4 w-4 mr-2" />
                              Analyze Document
                            </>
                          )}
                        </Button>
                      </div>
                    </div>
                    
                    <Separator />
                    
                    {/* Enhanced Contract Form */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div>
                        <Label htmlFor="name" className="text-sm font-medium text-slate-700">
                          Contract Name *
                        </Label>
                        <Input
                          id="name"
                          value={formData.name}
                          onChange={(e) => setFormData(prev => ({...prev, name: e.target.value}))}
                          className={`mt-1 ${formErrors.name ? 'border-red-500' : ''}`}
                          placeholder="e.g., Software Development Agreement"
                        />
                        {formErrors.name && (
                          <p className="text-xs text-red-600 mt-1">{formErrors.name}</p>
                        )}
                      </div>
                      
                      <div>
                        <Label htmlFor="client" className="text-sm font-medium text-slate-700">
                          Client Name *
                        </Label>
                        <Input
                          id="client"
                          value={formData.client}
                          onChange={(e) => setFormData(prev => ({...prev, client: e.target.value}))}
                          className={`mt-1 ${formErrors.client ? 'border-red-500' : ''}`}
                          placeholder="e.g., Acme Corporation"
                        />
                        {formErrors.client && (
                          <p className="text-xs text-red-600 mt-1">{formErrors.client}</p>
                        )}
                      </div>
                      
                      <div className="md:col-span-2">
                        <Label htmlFor="contact_email" className="text-sm font-medium text-slate-700 flex items-center gap-2">
                          Contact Email *
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <HelpCircle className="h-3 w-3 text-slate-400 cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent>
                              <p>This email will receive automated expiry reminders 30 days before contract expiration</p>
                            </TooltipContent>
                          </Tooltip>
                        </Label>
                        <Input
                          id="contact_email"
                          type="email"
                          value={formData.contact_email}
                          onChange={(e) => setFormData(prev => ({...prev, contact_email: e.target.value}))}
                          className={`mt-1 ${formErrors.contact_email ? 'border-red-500' : ''}`}
                          placeholder="contact@client.com"
                        />
                        {formErrors.contact_email ? (
                          <p className="text-xs text-red-600 mt-1">{formErrors.contact_email}</p>
                        ) : (
                          <p className="text-xs text-slate-500 mt-1">
                            📧 Automated expiry reminders will be sent to this email
                          </p>
                        )}
                      </div>
                      
                      <div>
                        <Label htmlFor="start_date" className="text-sm font-medium text-slate-700">
                          Start Date *
                        </Label>
                        <Input
                          id="start_date"
                          type="date"
                          value={formData.start_date}
                          onChange={(e) => setFormData(prev => ({...prev, start_date: e.target.value}))}
                          className={`mt-1 ${formErrors.start_date ? 'border-red-500' : ''}`}
                        />
                        {formErrors.start_date && (
                          <p className="text-xs text-red-600 mt-1">{formErrors.start_date}</p>
                        )}
                      </div>
                      
                      <div>
                        <Label htmlFor="expiry_date" className="text-sm font-medium text-slate-700">
                          Expiry Date *
                        </Label>
                        <Input
                          id="expiry_date"
                          type="date"
                          value={formData.expiry_date}
                          onChange={(e) => setFormData(prev => ({...prev, expiry_date: e.target.value}))}
                          className={`mt-1 ${formErrors.expiry_date ? 'border-red-500' : ''}`}
                        />
                        {formErrors.expiry_date && (
                          <p className="text-xs text-red-600 mt-1">{formErrors.expiry_date}</p>
                        )}
                      </div>
                    </div>
                    
                    <div className="flex gap-3 pt-6 border-t">
                      <Button 
                        type="submit" 
                        disabled={loading} 
                        className="flex-1 h-11"
                      >
                        {loading ? (
                          <>
                            <LoadingSpinner />
                            <span className="ml-2">Saving...</span>
                          </>
                        ) : (
                          <>
                            {currentContract ? <Edit className="h-4 w-4 mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
                            {currentContract ? 'Update Contract' : 'Create Contract'}
                          </>
                        )}
                      </Button>
                      <Button 
                        type="button" 
                        variant="outline" 
                        onClick={() => setIsModalOpen(false)}
                        className="flex-1 h-11"
                        disabled={loading}
                      >
                        Cancel
                      </Button>
                    </div>
                  </form>
                </DialogContent>
              </Dialog>
            </div>
          </div>

          {/* Enhanced Renewal Modal */}
          <Dialog open={isRenewalModalOpen} onOpenChange={setIsRenewalModalOpen}>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <RotateCcw className="h-5 w-5 text-green-600" />
                  Renew Contract
                </DialogTitle>
              </DialogHeader>
              
              {renewalContract && (
                <form onSubmit={handleRenewalSubmit} className="space-y-6">
                  <div className="bg-slate-50 p-4 rounded-lg">
                    <h4 className="font-medium text-slate-800">{renewalContract.name}</h4>
                    <p className="text-sm text-slate-600">Client: {renewalContract.client}</p>
                    <p className="text-xs text-slate-500 mt-1">
                      Current expiry: {format(parseISO(renewalContract.expiry_date), 'MMM dd, yyyy')}
                    </p>
                  </div>
                  
                  <div>
                    <Label htmlFor="new_expiry_date" className="text-sm font-medium text-slate-700">
                      New Expiry Date *
                    </Label>
                    <Input
                      id="new_expiry_date"
                      type="date"
                      value={renewalData.new_expiry_date}
                      onChange={(e) => setRenewalData(prev => ({...prev, new_expiry_date: e.target.value}))}
                      className="mt-1"
                      min={new Date().toISOString().split('T')[0]}
                    />
                    <p className="text-xs text-slate-500 mt-1">
                      Select a future date for the renewed contract
                    </p>
                  </div>
                  
                  <div>
                    <Label htmlFor="renewal_contact_email" className="text-sm font-medium text-slate-700">
                      Contact Email
                    </Label>
                    <Input
                      id="renewal_contact_email"
                      type="email"
                      value={renewalData.contact_email}
                      onChange={(e) => setRenewalData(prev => ({...prev, contact_email: e.target.value}))}
                      placeholder="Update contact email (optional)"
                      className="mt-1"
                    />
                  </div>
                  
                  <div className="flex gap-3 pt-4 border-t">
                    <Button 
                      type="submit" 
                      disabled={loading} 
                      className="flex-1 bg-green-600 hover:bg-green-700"
                    >
                      {loading ? (
                        <>
                          <LoadingSpinner />
                          <span className="ml-2">Renewing...</span>
                        </>
                      ) : (
                        <>
                          <RotateCcw className="h-4 w-4 mr-2" />
                          Renew Contract
                        </>
                      )}
                    </Button>
                    <Button 
                      type="button" 
                      variant="outline" 
                      onClick={() => setIsRenewalModalOpen(false)}
                      className="flex-1"
                      disabled={loading}
                    >
                      Cancel
                    </Button>
                  </div>
                </form>
              )}
            </DialogContent>
          </Dialog>

          {/* Enhanced Contracts Grid */}
          {filteredContracts.length === 0 ? (
            <EmptyState />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredContracts.map((contract) => {
                const daysUntilExpiry = differenceInDays(parseISO(contract.expiry_date), new Date());
                const isExpiring = daysUntilExpiry <= 30 && daysUntilExpiry >= 0;
                const isExpired = contract.status === 'Expired' || daysUntilExpiry < 0;
                
                return (
                  <Card 
                    key={contract.id} 
                    className={`hover:shadow-lg transition-all duration-300 hover:scale-[1.02] ${getCardBorderClass(contract.expiry_date, contract.status)}`}
                  >
                    <CardHeader className="pb-3">
                      <div className="flex justify-between items-start">
                        <div className="flex-1 min-w-0">
                          <CardTitle className="text-lg font-semibold text-slate-800 mb-1 truncate">
                            {contract.name}
                          </CardTitle>
                          <CardDescription className="text-slate-600 mb-1">
                            {contract.client}
                          </CardDescription>
                          <div className="flex items-center gap-1 text-xs text-slate-500">
                            <Mail className="h-3 w-3" />
                            <span className="truncate">{contract.contact_email}</span>
                          </div>
                        </div>
                        <Badge 
                          className={`text-white text-xs px-2 py-1 ${getStatusColor(contract.expiry_date, contract.status)}`}
                        >
                          {contract.status}
                        </Badge>
                      </div>
                    </CardHeader>
                    
                    <CardContent>
                      <div className="space-y-3">
                        <div className="flex items-center gap-2 text-sm text-slate-600">
                          <Calendar className="h-4 w-4" />
                          <span className="text-xs">
                            {format(parseISO(contract.start_date), 'MMM dd, yyyy')} - {' '}
                            {format(parseISO(contract.expiry_date), 'MMM dd, yyyy')}
                          </span>
                        </div>
                        
                        <div className="flex items-center justify-between">
                          <span className={`font-medium text-sm ${
                            isExpired ? 'text-red-600' : 
                            daysUntilExpiry <= 7 ? 'text-red-500' :
                            daysUntilExpiry <= 30 ? 'text-yellow-600' : 'text-green-600'
                          }`}>
                            {getDaysUntilExpiry(contract.expiry_date)}
                          </span>
                          
                          <div className="flex gap-1">
                            {isExpired && (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    size="sm"
                                    onClick={() => handleRenewal(contract)}
                                    className="bg-green-600 hover:bg-green-700 text-white h-8 px-3"
                                  >
                                    <RotateCcw className="h-3 w-3 mr-1" />
                                    Renew
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p>Renew this expired contract</p>
                                </TooltipContent>
                              </Tooltip>
                            )}
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleEdit(contract);
                                  }}
                                  className="h-8 w-8 p-0"
                                >
                                  <Edit className="h-3 w-3" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p>Edit contract details</p>
                              </TooltipContent>
                            </Tooltip>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleDelete(contract);
                                  }}
                                  className="hover:bg-red-50 hover:border-red-200 h-8 w-8 p-0"
                                >
                                  <Trash2 className="h-3 w-3" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p>Delete contract</p>
                              </TooltipContent>
                            </Tooltip>
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}

          {/* Professional Footer */}
          <footer className="mt-16 pt-8 border-t border-slate-200">
            <div className="text-center space-y-4">
              <div className="flex items-center justify-center gap-2 text-slate-600">
                <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                  <FileText className="h-4 w-4 text-white" />
                </div>
                <span className="font-semibold">Corvus Contract Management System</span>
              </div>
              
              <div className="flex items-center justify-center gap-6 text-sm text-slate-500">
                <span className="flex items-center gap-1">
                  <Sparkles className="h-4 w-4" />
                  AI-Powered Analysis
                </span>
                <span className="flex items-center gap-1">
                  <Mail className="h-4 w-4" />
                  Automated Reminders
                </span>
                <span className="flex items-center gap-1">
                  <RotateCcw className="h-4 w-4" />
                  Smart Renewals
                </span>
              </div>
              
              <div className="text-xs text-slate-400 space-y-1">
                <p>© 2024 KrijoTech. Built with React, FastAPI, and AI technology.</p>
                <p>Created with ❤️ for efficient contract management</p>
              </div>
            </div>
          </footer>
        </div>
        
        <Toaster />
      </div>
    </TooltipProvider>
  );
}

export default App;