import React, { useState, useEffect } from 'react';
import './App.css';
import axios from 'axios';
import { format, differenceInDays, parseISO } from 'date-fns';
import { Plus, Search, Calendar, AlertTriangle, Edit, Trash2, FileText, Sparkles } from 'lucide-react';
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

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function App() {
  const [contracts, setContracts] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [currentContract, setCurrentContract] = useState(null);
  const [loading, setLoading] = useState(false);
  const [documentText, setDocumentText] = useState('');
  const [analyzing, setAnalyzing] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    client: '',
    start_date: '',
    expiry_date: '',
    status: 'Active'
  });
  
  const { toast } = useToast();

  // Fetch contracts
  const fetchContracts = async () => {
    try {
      const response = await axios.get(`${API}/contracts`);
      setContracts(response.data);
    } catch (error) {
      console.error('Error fetching contracts:', error);
      toast({
        title: "Error",
        description: "Failed to fetch contracts",
        variant: "destructive"
      });
    }
  };

  useEffect(() => {
    fetchContracts();
  }, []);

  // Filter contracts based on search term
  const filteredContracts = contracts.filter(contract =>
    contract.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    contract.client.toLowerCase().includes(searchTerm.toLowerCase())
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
  const getStatusColor = (expiryDate) => {
    const days = differenceInDays(parseISO(expiryDate), new Date());
    if (days < 0) return 'bg-red-500';
    if (days <= 7) return 'bg-red-400';
    if (days <= 30) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  // Handle form submission
  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    try {
      if (currentContract) {
        await axios.put(`${API}/contracts/${currentContract.id}`, formData);
        toast({
          title: "Success",
          description: "Contract updated successfully"
        });
      } else {
        await axios.post(`${API}/contracts`, formData);
        toast({
          title: "Success", 
          description: "Contract created successfully"
        });
      }
      
      fetchContracts();
      resetForm();
      setIsModalOpen(false);
    } catch (error) {
      console.error('Error saving contract:', error);
      toast({
        title: "Error",
        description: "Failed to save contract",
        variant: "destructive"
      });
    } finally {
      setLoading(false);
    }
  };

  // Handle delete
  const handleDelete = async (id) => {
    if (!window.confirm('Are you sure you want to delete this contract?')) return;
    
    try {
      await axios.delete(`${API}/contracts/${id}`);
      toast({
        title: "Success",
        description: "Contract deleted successfully"
      });
      fetchContracts();
    } catch (error) {
      console.error('Error deleting contract:', error);
      toast({
        title: "Error",
        description: "Failed to delete contract",
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
      start_date: contract.start_date,
      expiry_date: contract.expiry_date,
      status: contract.status
    });
    setIsModalOpen(true);
  };

  // Reset form
  const resetForm = () => {
    setCurrentContract(null);
    setFormData({
      name: '',
      client: '',
      start_date: '',
      expiry_date: '',
      status: 'Active'
    });
    setDocumentText('');
  };

  // Handle document analysis
  const handleAnalyzeDocument = async () => {
    if (!documentText.trim()) {
      toast({
        title: "Error",
        description: "Please enter document text to analyze",
        variant: "destructive"
      });
      return;
    }

    setAnalyzing(true);
    
    try {
      const response = await axios.post(`${API}/analyze-document`, {
        document_text: documentText
      });
      
      const { contract_date, contract_tenure, expiry_date, error } = response.data;
      
      if (error) {
        toast({
          title: "Analysis Error",
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
          description: `Found contract date: ${contract_date}${contract_tenure ? `, tenure: ${contract_tenure}` : ''}`
        });
      } else {
        toast({
          title: "No Information Found",
          description: "Could not extract contract dates from the document",
          variant: "destructive"
        });
      }
    } catch (error) {
      console.error('Error analyzing document:', error);
      toast({
        title: "Error",
        description: "Failed to analyze document",
        variant: "destructive"
      });
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-slate-800 mb-2">Contract Management Dashboard</h1>
          <p className="text-slate-600">Manage your contracts with AI-powered document analysis</p>
        </div>

        {/* Expiring Contracts Alert */}
        {expiringContracts.length > 0 && (
          <Alert className="mb-6 border-yellow-500 bg-yellow-50">
            <AlertTriangle className="h-4 w-4 text-yellow-600" />
            <AlertDescription className="text-yellow-800">
              <strong>Contracts expiring soon:</strong> {expiringContracts.map(c => c.name).join(', ')}
            </AlertDescription>
          </Alert>
        )}

        {/* Controls */}
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400 h-4 w-4" />
            <Input
              placeholder="Search contracts by name or client..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
          </div>
          
          <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
            <DialogTrigger asChild>
              <Button onClick={resetForm} className="bg-blue-600 hover:bg-blue-700">
                <Plus className="h-4 w-4 mr-2" />
                Add Contract
              </Button>
            </DialogTrigger>
            
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>
                  {currentContract ? 'Edit Contract' : 'Add New Contract'}
                </DialogTitle>
              </DialogHeader>
              
              <form onSubmit={handleSubmit} className="space-y-6">
                {/* Document Analysis Section */}
                <div className="bg-blue-50 p-4 rounded-lg border">
                  <div className="flex items-center gap-2 mb-3">
                    <Sparkles className="h-5 w-5 text-blue-600" />
                    <h3 className="font-semibold text-blue-800">AI Document Analysis</h3>
                  </div>
                  
                  <div className="space-y-3">
                    <Label htmlFor="document-text">Contract Document Text</Label>
                    <Textarea
                      id="document-text"
                      placeholder="Paste your contract text here for AI analysis..."
                      value={documentText}
                      onChange={(e) => setDocumentText(e.target.value)}
                      rows={4}
                      className="resize-none"
                    />
                    <Button
                      type="button"
                      onClick={handleAnalyzeDocument}
                      disabled={analyzing || !documentText.trim()}
                      variant="outline"
                      className="w-full"
                    >
                      {analyzing ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
                          Analyzing...
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
                
                {/* Contract Form */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="name">Contract Name *</Label>
                    <Input
                      id="name"
                      value={formData.name}
                      onChange={(e) => setFormData(prev => ({...prev, name: e.target.value}))}
                      required
                    />
                  </div>
                  
                  <div>
                    <Label htmlFor="client">Client Name *</Label>
                    <Input
                      id="client"
                      value={formData.client}
                      onChange={(e) => setFormData(prev => ({...prev, client: e.target.value}))}
                      required
                    />
                  </div>
                  
                  <div>
                    <Label htmlFor="start_date">Start Date *</Label>
                    <Input
                      id="start_date"
                      type="date"
                      value={formData.start_date}
                      onChange={(e) => setFormData(prev => ({...prev, start_date: e.target.value}))}
                      required
                    />
                  </div>
                  
                  <div>
                    <Label htmlFor="expiry_date">Expiry Date *</Label>
                    <Input
                      id="expiry_date"
                      type="date"
                      value={formData.expiry_date}
                      onChange={(e) => setFormData(prev => ({...prev, expiry_date: e.target.value}))}
                      required
                    />
                  </div>
                </div>
                
                <div className="flex gap-3 pt-4">
                  <Button type="submit" disabled={loading} className="flex-1">
                    {loading ? 'Saving...' : (currentContract ? 'Update Contract' : 'Create Contract')}
                  </Button>
                  <Button 
                    type="button" 
                    variant="outline" 
                    onClick={() => setIsModalOpen(false)}
                    className="flex-1"
                  >
                    Cancel
                  </Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {/* Contracts Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredContracts.map((contract) => {
            const daysUntilExpiry = differenceInDays(parseISO(contract.expiry_date), new Date());
            const isExpiring = daysUntilExpiry <= 30 && daysUntilExpiry >= 0;
            
            return (
              <Card 
                key={contract.id} 
                className={`hover:shadow-lg transition-all duration-200 ${
                  isExpiring ? 'ring-2 ring-yellow-400 shadow-yellow-100' : ''
                } ${daysUntilExpiry < 0 ? 'ring-2 ring-red-400 shadow-red-100' : ''}`}
              >
                <CardHeader className="pb-3">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <CardTitle className="text-lg font-semibold text-slate-800 mb-1">
                        {contract.name}
                      </CardTitle>
                      <CardDescription className="text-slate-600">
                        {contract.client}
                      </CardDescription>
                    </div>
                    <Badge 
                      className={`text-white ${getStatusColor(contract.expiry_date)}`}
                    >
                      {contract.status}
                    </Badge>
                  </div>
                </CardHeader>
                
                <CardContent>
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 text-sm text-slate-600">
                      <Calendar className="h-4 w-4" />
                      <span>
                        {format(parseISO(contract.start_date), 'MMM dd, yyyy')} - {' '}
                        {format(parseISO(contract.expiry_date), 'MMM dd, yyyy')}
                      </span>
                    </div>
                    
                    <div className="flex items-center justify-between">
                      <span className={`font-medium ${
                        daysUntilExpiry < 0 ? 'text-red-600' : 
                        daysUntilExpiry <= 7 ? 'text-red-500' :
                        daysUntilExpiry <= 30 ? 'text-yellow-600' : 'text-green-600'
                      }`}>
                        {getDaysUntilExpiry(contract.expiry_date)}
                      </span>
                      
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleEdit(contract);
                          }}
                        >
                          <Edit className="h-3 w-3" />
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(contract.id);
                          }}
                          className="hover:bg-red-50 hover:border-red-200"
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {/* Empty State */}
        {filteredContracts.length === 0 && (
          <div className="text-center py-12">
            <FileText className="h-16 w-16 text-slate-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-600 mb-2">
              {searchTerm ? 'No contracts found' : 'No contracts yet'}
            </h3>
            <p className="text-slate-500 mb-4">
              {searchTerm 
                ? 'Try adjusting your search terms' 
                : 'Create your first contract to get started'
              }
            </p>
            {!searchTerm && (
              <Button onClick={() => {resetForm(); setIsModalOpen(true);}} className="bg-blue-600 hover:bg-blue-700">
                <Plus className="h-4 w-4 mr-2" />
                Add Your First Contract
              </Button>
            )}
          </div>
        )}
      </div>
      
      <Toaster />
    </div>
  );
}

export default App;