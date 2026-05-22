"""Static catalogs the Engineer agent grounds against to avoid hallucinated imports.

Two catalogs:
  - SHADCN_COMPONENTS: import paths + variant API + example for each shadcn primitive
  - LUCIDE_ICONS: whitelisted lucide-react icon names

These are inlined as text in the Engineer prompt (we tried tool-calling — the LLM
forgot to call). The text blocks are ~3-4k tokens combined, small enough to ship
in every prompt and large enough to eliminate most hallucinated imports.
"""

from __future__ import annotations


SHADCN_COMPONENTS: dict[str, dict] = {
    "button": {
        "import": "import { Button } from '@/components/ui/button'",
        "variants": ["default", "destructive", "outline", "secondary", "ghost", "link"],
        "sizes": ["default", "sm", "lg", "icon"],
        "example": "<Button variant='outline' size='lg' onClick={handler}>Get started</Button>",
    },
    "card": {
        "import": "import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'",
        "example": "<Card><CardHeader><CardTitle>Title</CardTitle><CardDescription>desc</CardDescription></CardHeader><CardContent>body</CardContent></Card>",
    },
    "dialog": {
        "import": "import { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'",
        "example": "<Dialog><DialogTrigger asChild><Button>Open</Button></DialogTrigger><DialogContent><DialogHeader><DialogTitle>T</DialogTitle></DialogHeader>...</DialogContent></Dialog>",
    },
    "sheet": {
        "import": "import { Sheet, SheetTrigger, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'",
        "note": "side prop: 'top' | 'right' | 'bottom' | 'left'",
    },
    "input": {
        "import": "import { Input } from '@/components/ui/input'",
        "example": "<Input type='email' placeholder='you@example.com' {...register('email')} />",
    },
    "label": {
        "import": "import { Label } from '@/components/ui/label'",
        "example": "<Label htmlFor='email'>Email</Label>",
    },
    "textarea": {
        "import": "import { Textarea } from '@/components/ui/textarea'",
    },
    "tabs": {
        "import": "import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'",
        "example": "<Tabs defaultValue='a'><TabsList><TabsTrigger value='a'>A</TabsTrigger></TabsList><TabsContent value='a'>...</TabsContent></Tabs>",
    },
    "accordion": {
        "import": "import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion'",
        "example": "<Accordion type='single' collapsible><AccordionItem value='1'><AccordionTrigger>Q?</AccordionTrigger><AccordionContent>A.</AccordionContent></AccordionItem></Accordion>",
    },
    "select": {
        "import": "import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'",
        "example": "<Select onValueChange={setV}><SelectTrigger><SelectValue placeholder='Pick' /></SelectTrigger><SelectContent><SelectItem value='a'>A</SelectItem></SelectContent></Select>",
    },
    "dropdown-menu": {
        "import": "import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator } from '@/components/ui/dropdown-menu'",
    },
    "navigation-menu": {
        "import": "import { NavigationMenu, NavigationMenuList, NavigationMenuItem, NavigationMenuLink, NavigationMenuTrigger, NavigationMenuContent } from '@/components/ui/navigation-menu'",
    },
    "badge": {
        "import": "import { Badge } from '@/components/ui/badge'",
        "variants": ["default", "secondary", "destructive", "outline"],
        "example": "<Badge variant='secondary'>New</Badge>",
    },
    "avatar": {
        "import": "import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'",
        "example": "<Avatar><AvatarImage src={url} /><AvatarFallback>SC</AvatarFallback></Avatar>",
    },
    "tooltip": {
        "import": "import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip'",
        "note": "Mount <TooltipProvider> at the App root once.",
    },
    "switch": {
        "import": "import { Switch } from '@/components/ui/switch'",
        "example": "<Switch checked={on} onCheckedChange={setOn} />",
    },
    "checkbox": {
        "import": "import { Checkbox } from '@/components/ui/checkbox'",
        "example": "<Checkbox checked={c} onCheckedChange={setC} />",
    },
    "radio-group": {
        "import": "import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'",
    },
    "slider": {
        "import": "import { Slider } from '@/components/ui/slider'",
        "example": "<Slider defaultValue={[50]} max={100} step={1} onValueChange={setV} />",
    },
    "separator": {
        "import": "import { Separator } from '@/components/ui/separator'",
    },
    "skeleton": {
        "import": "import { Skeleton } from '@/components/ui/skeleton'",
        "example": "<Skeleton className='h-8 w-32' />",
    },
    "scroll-area": {
        "import": "import { ScrollArea } from '@/components/ui/scroll-area'",
    },
    "popover": {
        "import": "import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'",
    },
    "alert": {
        "import": "import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'",
    },
    "progress": {
        "import": "import { Progress } from '@/components/ui/progress'",
    },
    "table": {
        "import": "import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'",
    },
    "sonner": {
        "import": "import { Toaster, toast } from 'sonner'",
        "note": "Mount <Toaster richColors position='top-right' /> ONCE in App.tsx. Call toast.success(...) / toast.error(...) anywhere.",
    },
}


# Curated whitelist of lucide-react icons. The Engineer agent must pick only
# from this list; any other name will fail to import at build time.
LUCIDE_ICONS: list[str] = sorted([
    # arrows & navigation
    "ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown", "ArrowUpRight", "ArrowDownRight",
    "ChevronRight", "ChevronLeft", "ChevronUp", "ChevronDown",
    "ChevronsRight", "ChevronsLeft", "ChevronsUp", "ChevronsDown",
    "Menu", "X", "MoreHorizontal", "MoreVertical",
    # actions
    "Check", "CheckCheck", "Plus", "PlusCircle", "Minus", "Edit", "Edit3",
    "Trash", "Trash2", "Copy", "ClipboardCopy", "Download", "Upload",
    "Share", "Share2", "ExternalLink", "Link", "Link2", "Settings", "Settings2",
    "Filter", "Search", "RefreshCw", "Save", "RotateCw", "Undo", "Redo",
    # status
    "AlertTriangle", "AlertCircle", "AlertOctagon", "Info", "CheckCircle",
    "CheckCircle2", "XCircle", "Loader2", "Loader", "Sparkles", "Sparkle",
    "Zap", "Star", "Heart", "Bookmark", "Flag", "ThumbsUp", "ThumbsDown",
    # comms
    "Mail", "MailOpen", "MessageSquare", "MessageCircle", "Phone", "PhoneCall",
    "Send", "Bell", "BellOff", "BellRing", "Inbox", "AtSign",
    # users
    "User", "UserCircle", "Users", "UserPlus", "UserCheck", "UserX",
    "LogIn", "LogOut",
    # commerce
    "ShoppingCart", "ShoppingBag", "CreditCard", "Wallet", "DollarSign",
    "Tag", "Tags", "Gift", "Package", "PackageCheck", "Truck", "Receipt",
    "Percent",
    # data / charts
    "BarChart", "BarChart2", "BarChart3", "LineChart", "PieChart",
    "TrendingUp", "TrendingDown", "Activity", "Eye", "EyeOff",
    # files
    "File", "FileText", "FilePlus", "Folder", "FolderOpen", "FolderPlus",
    "Image", "ImagePlus", "Paperclip", "FileCheck",
    # security
    "Lock", "Unlock", "Shield", "ShieldCheck", "ShieldAlert", "Key", "KeyRound",
    # time
    "Calendar", "CalendarDays", "Clock", "Hourglass", "Timer",
    # places
    "Home", "MapPin", "Map", "Globe", "Building", "Building2", "Store",
    # tech
    "Code", "Code2", "Terminal", "TerminalSquare", "Cpu", "Database", "Server",
    "Cloud", "CloudUpload", "CloudDownload", "GitBranch", "GitMerge",
    "GitPullRequest", "Github", "GitFork",
    # social
    "Twitter", "Facebook", "Instagram", "Linkedin", "Youtube", "Twitch",
    # weather/visual
    "Sun", "Moon", "CloudRain", "CloudSnow", "Palette", "Paintbrush",
    # misc
    "Wand", "Wand2", "Layers", "Layers2", "Layout", "LayoutDashboard",
    "LayoutGrid", "LayoutList", "List", "ListChecks", "Grid", "Grid2x2", "Grid3x3",
    "Rocket", "Target", "Award", "Trophy", "Flame", "Gauge", "Headphones",
    "Music", "Music2", "Play", "Pause", "SkipForward", "SkipBack",
    "Volume2", "VolumeX", "Mic", "MicOff", "Video", "VideoOff", "Camera",
    "Wifi", "WifiOff", "Bluetooth", "Battery", "BatteryCharging",
    "Brain", "Lightbulb", "Coffee", "Book", "BookOpen", "GraduationCap",
    "Briefcase", "Building", "Hammer", "Wrench", "Cog",
    "Smile", "Frown", "Meh",
])


def shadcn_catalog_text() -> str:
    """Compact text block injected into the Engineer prompt."""
    lines = ["AVAILABLE shadcn/ui COMPONENTS — these are the ONLY ones you may import. Import paths are exact:"]
    for name, info in SHADCN_COMPONENTS.items():
        lines.append(f"\n  [{name}]")
        lines.append(f"    {info['import']}")
        if "variants" in info:
            lines.append(f"    variants: {info['variants']}")
        if "sizes" in info:
            lines.append(f"    sizes: {info['sizes']}")
        if "example" in info:
            lines.append(f"    example: {info['example']}")
        if "note" in info:
            lines.append(f"    note: {info['note']}")
    return "\n".join(lines)


def lucide_catalog_text() -> str:
    """Whitelisted lucide-react icon names."""
    return (
        "AVAILABLE lucide-react ICONS — pick ONLY from this list "
        "(any other name will fail to import):\n  "
        + ", ".join(LUCIDE_ICONS)
    )
