import React, { useState, useEffect } from 'react';
import { 
  Package, 
  Cpu, 
  DollarSign, 
  Clock, 
  CheckCircle, 
  AlertCircle,
  XCircle,
  Upload,
  Settings,
  BarChart,
  Layers,
  Box,
  Zap,
  Send,
  MessageCircle,
  ChevronRight,
  Activity,
  Palette,
  Wrench
} from 'lucide-react';

// CSS Variables for ProtoGen Color Scheme
const cssVariables = `
  :root {
    /* Primary Colors */
    --spectrum-blue: #00AEEF;
    --spectrum-red: #E53935;
    --spectrum-yellow: #FFEB3B;
    --spectrum-green: #4CAF50;
    --spectrum-orange: #FF9800;
    
    /* Gradient Core Colors */
    --gradient-start: #00BFFF;
    --gradient-mid: #8A2BE2;
    --gradient-end: #FF4500;
    
    /* Secondary & Neutral Colors */
    --dark-gray: #2E2E2E;
    --light-gray: #B0BEC5;
    --white: #FFFFFF;
    
    /* Gradients */
    --spectrum-gradient: linear-gradient(135deg, var(--gradient-start), var(--gradient-mid), var(--gradient-end));
    --button-hover-gradient: linear-gradient(135deg, var(--spectrum-blue), var(--spectrum-green));
    --subtle-gradient: linear-gradient(180deg, rgba(0, 174, 239, 0.1), rgba(138, 43, 226, 0.05));
  }
`;

// Inject CSS variables
const styleSheet = document.createElement("style");
styleSheet.textContent = cssVariables;
document.head.appendChild(styleSheet);

const ProtoGenUI = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [selectedProject, setSelectedProject] = useState(null);
  const [aiPanelOpen, setAiPanelOpen] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  // Mock data for demonstration
  const projects = [
    {
      id: 1,
      name: "Racing Drone Frame",
      status: "manufacturing",
      progress: 65,
      cost: "$1,250",
      deadline: "3 days",
      material: "Carbon Fiber"
    },
    {
      id: 2,
      name: "IoT Sensor Housing",
      status: "designing",
      progress: 30,
      cost: "$450",
      deadline: "5 days",
      material: "ABS Plastic"
    }
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header with Gradient */}
      <header className="relative overflow-hidden bg-gray-900">
        <div 
          className="absolute inset-0 opacity-20"
          style={{ background: 'var(--spectrum-gradient)' }}
        />
        <div className="relative z-10 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              {/* Logo Placeholder */}
              <div className="w-10 h-10 rounded-lg flex items-center justify-center"
                   style={{ background: 'var(--spectrum-gradient)' }}>
                <Box className="w-6 h-6 text-white" />
              </div>
              <h1 className="text-2xl font-bold text-white">ProtoGen</h1>
            </div>
            
            {/* Navigation */}
            <nav className="flex items-center space-x-6">
              <button
                onClick={() => setActiveTab('dashboard')}
                className={`text-white hover:text-gray-200 transition-colors ${
                  activeTab === 'dashboard' ? 'border-b-2' : ''
                }`}
                style={{ borderColor: activeTab === 'dashboard' ? 'var(--spectrum-blue)' : 'transparent' }}
              >
                Dashboard
              </button>
              <button
                onClick={() => setActiveTab('projects')}
                className={`text-white hover:text-gray-200 transition-colors ${
                  activeTab === 'projects' ? 'border-b-2' : ''
                }`}
                style={{ borderColor: activeTab === 'projects' ? 'var(--spectrum-blue)' : 'transparent' }}
              >
                Projects
              </button>
              <button
                onClick={() => setActiveTab('materials')}
                className={`text-white hover:text-gray-200 transition-colors ${
                  activeTab === 'materials' ? 'border-b-2' : ''
                }`}
                style={{ borderColor: activeTab === 'materials' ? 'var(--spectrum-blue)' : 'transparent' }}
              >
                Materials
              </button>
            </nav>

            {/* AI Assistant Button */}
            <button
              onClick={() => setAiPanelOpen(!aiPanelOpen)}
              className="flex items-center space-x-2 px-4 py-2 rounded-lg text-white transition-all"
              style={{ 
                backgroundColor: 'var(--spectrum-blue)',
                boxShadow: aiPanelOpen ? '0 0 20px rgba(0, 174, 239, 0.5)' : 'none'
              }}
            >
              <MessageCircle className="w-5 h-5" />
              <span>AI Assistant</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-8">
        {/* Quick Actions Bar */}
        <div className="mb-8 p-6 bg-white rounded-xl shadow-sm">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <button 
              className="group flex items-center justify-center space-x-3 p-4 rounded-lg border-2 border-gray-200 hover:border-transparent transition-all"
              style={{ 
                background: 'white',
                ':hover': { background: 'var(--button-hover-gradient)' }
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--button-hover-gradient)';
                e.currentTarget.style.color = 'white';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'white';
                e.currentTarget.style.color = 'var(--dark-gray)';
              }}
            >
              <Upload className="w-5 h-5" />
              <span className="font-medium">Upload Design</span>
            </button>
            
            <button 
              className="flex items-center justify-center space-x-3 p-4 rounded-lg border-2 border-gray-200 hover:border-transparent transition-all"
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--button-hover-gradient)';
                e.currentTarget.style.color = 'white';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'white';
                e.currentTarget.style.color = 'var(--dark-gray)';
              }}
            >
              <Zap className="w-5 h-5" />
              <span className="font-medium">Quick Quote</span>
            </button>
            
            <button 
              className="flex items-center justify-center space-x-3 p-4 rounded-lg border-2 border-gray-200 hover:border-transparent transition-all"
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--button-hover-gradient)';
                e.currentTarget.style.color = 'white';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'white';
                e.currentTarget.style.color = 'var(--dark-gray)';
              }}
            >
              <Palette className="w-5 h-5" />
              <span className="font-medium">Materials</span>
            </button>
            
            <button 
              className="flex items-center justify-center space-x-3 p-4 rounded-lg border-2 border-gray-200 hover:border-transparent transition-all"
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--button-hover-gradient)';
                e.currentTarget.style.color = 'white';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'white';
                e.currentTarget.style.color = 'var(--dark-gray)';
              }}
            >
              <Activity className="w-5 h-5" />
              <span className="font-medium">Track Orders</span>
            </button>
          </div>
        </div>

        {/* Project Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map((project) => (
            <div 
              key={project.id}
              className="bg-white rounded-xl shadow-sm hover:shadow-lg transition-shadow cursor-pointer overflow-hidden"
              onClick={() => setSelectedProject(project)}
            >
              {/* Card Header with Gradient Accent */}
              <div 
                className="h-2"
                style={{ background: 'var(--spectrum-gradient)' }}
              />
              
              <div className="p-6">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h3 className="text-lg font-semibold" style={{ color: 'var(--dark-gray)' }}>
                      {project.name}
                    </h3>
                    <p className="text-sm" style={{ color: 'var(--light-gray)' }}>
                      {project.material}
                    </p>
                  </div>
                  {getStatusIcon(project.status)}
                </div>

                {/* Progress Bar */}
                <div className="mb-4">
                  <div className="flex justify-between text-sm mb-1">
                    <span style={{ color: 'var(--light-gray)' }}>Progress</span>
                    <span style={{ color: 'var(--dark-gray)' }}>{project.progress}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div 
                      className="h-2 rounded-full transition-all duration-500"
                      style={{ 
                        width: `${project.progress}%`,
                        background: 'var(--spectrum-gradient)'
                      }}
                    />
                  </div>
                </div>

                {/* Stats */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="flex items-center space-x-2">
                    <DollarSign className="w-4 h-4" style={{ color: 'var(--spectrum-green)' }} />
                    <span className="text-sm font-medium">{project.cost}</span>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Clock className="w-4 h-4" style={{ color: 'var(--spectrum-orange)' }} />
                    <span className="text-sm font-medium">{project.deadline}</span>
                  </div>
                </div>

                {/* Action Button */}
                <button 
                  className="mt-4 w-full py-2 px-4 rounded-lg text-white font-medium transition-all"
                  style={{ backgroundColor: 'var(--spectrum-blue)' }}
                  onMouseEnter={(e) => e.currentTarget.style.opacity = '0.9'}
                  onMouseLeave={(e) => e.currentTarget.style.opacity = '1'}
                >
                  View Details
                </button>
              </div>
            </div>
          ))}

          {/* New Project Card */}
          <div 
            className="bg-white rounded-xl shadow-sm hover:shadow-lg transition-all cursor-pointer border-2 border-dashed"
            style={{ borderColor: 'var(--light-gray)' }}
          >
            <div className="p-6 flex flex-col items-center justify-center h-full">
              <div 
                className="w-16 h-16 rounded-full flex items-center justify-center mb-4"
                style={{ background: 'var(--subtle-gradient)' }}
              >
                <Package className="w-8 h-8" style={{ color: 'var(--spectrum-blue)' }} />
              </div>
              <h3 className="text-lg font-semibold mb-2" style={{ color: 'var(--dark-gray)' }}>
                Start New Project
              </h3>
              <p className="text-sm text-center mb-4" style={{ color: 'var(--light-gray)' }}>
                Upload a design or describe what you need
              </p>
              <button 
                className="px-6 py-2 rounded-lg text-white font-medium transition-all"
                style={{ backgroundColor: 'var(--spectrum-blue)' }}
              >
                Get Started
              </button>
            </div>
          </div>
        </div>

        {/* Alert Examples */}
        <div className="mt-8 space-y-4">
          <Alert type="success" message="Your design has been optimized successfully! Weight reduced by 18%." />
          <Alert type="warning" message="Material availability is limited. Consider alternative options." />
          <Alert type="error" message="Design validation failed. Wall thickness below minimum requirements." />
        </div>
      </main>

      {/* AI Assistant Panel */}
      {aiPanelOpen && (
        <div className="fixed right-0 top-0 h-full w-96 bg-white shadow-2xl z-50 transform transition-transform">
          <div 
            className="h-1"
            style={{ background: 'var(--spectrum-gradient)' }}
          />
          <div className="p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold" style={{ color: 'var(--dark-gray)' }}>
                AI Assistant
              </h2>
              <button 
                onClick={() => setAiPanelOpen(false)}
                className="text-gray-500 hover:text-gray-700"
              >
                <XCircle className="w-6 h-6" />
              </button>
            </div>
            
            <div className="bg-gray-50 rounded-lg p-4 mb-4">
              <p className="text-sm" style={{ color: 'var(--dark-gray)' }}>
                How can I help you with your manufacturing project today?
              </p>
            </div>

            <div className="space-y-3">
              <AIQuickAction 
                icon={<Wrench />}
                text="Optimize current design"
                subtext="Reduce weight and cost"
              />
              <AIQuickAction 
                icon={<Palette />}
                text="Recommend materials"
                subtext="Based on your requirements"
              />
              <AIQuickAction 
                icon={<BarChart />}
                text="Get instant quote"
                subtext="From verified suppliers"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Helper Components
const Alert = ({ type, message }) => {
  const styles = {
    success: { bg: 'rgba(76, 175, 80, 0.1)', border: 'var(--spectrum-green)', icon: CheckCircle },
    warning: { bg: 'rgba(255, 152, 0, 0.1)', border: 'var(--spectrum-orange)', icon: AlertCircle },
    error: { bg: 'rgba(229, 57, 53, 0.1)', border: 'var(--spectrum-red)', icon: XCircle }
  };

  const config = styles[type];
  const Icon = config.icon;

  return (
    <div 
      className="p-4 rounded-lg border-l-4 flex items-start space-x-3"
      style={{ 
        backgroundColor: config.bg,
        borderColor: config.border
      }}
    >
      <Icon className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: config.border }} />
      <p className="text-sm" style={{ color: 'var(--dark-gray)' }}>{message}</p>
    </div>
  );
};

const AIQuickAction = ({ icon, text, subtext }) => (
  <button 
    className="w-full p-3 rounded-lg border border-gray-200 hover:border-transparent transition-all text-left group"
    onMouseEnter={(e) => {
      e.currentTarget.style.background = 'var(--subtle-gradient)';
      e.currentTarget.style.borderColor = 'var(--spectrum-blue)';
    }}
    onMouseLeave={(e) => {
      e.currentTarget.style.background = 'white';
      e.currentTarget.style.borderColor = '#E5E7EB';
    }}
  >
    <div className="flex items-start space-x-3">
      <div className="text-gray-600 group-hover:text-blue-600 transition-colors">
        {React.cloneElement(icon, { className: 'w-5 h-5' })}
      </div>
      <div className="flex-1">
        <p className="font-medium text-sm" style={{ color: 'var(--dark-gray)' }}>{text}</p>
        <p className="text-xs mt-0.5" style={{ color: 'var(--light-gray)' }}>{subtext}</p>
      </div>
      <ChevronRight className="w-4 h-4 text-gray-400 group-hover:text-blue-600 transition-colors" />
    </div>
  </button>
);

const getStatusIcon = (status) => {
  const icons = {
    manufacturing: <Cpu className="w-5 h-5" style={{ color: 'var(--spectrum-blue)' }} />,
    designing: <Settings className="w-5 h-5" style={{ color: 'var(--spectrum-orange)' }} />,
    completed: <CheckCircle className="w-5 h-5" style={{ color: 'var(--spectrum-green)' }} />
  };
  return icons[status] || null;
};

export default ProtoGenUI;